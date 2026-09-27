import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etherlighting"))
from core import parse_macs, parse_ports, validate_rules, make_plan, led_command, restore_command
from app import Application, handler_for
from switch import SSHSwitch

A, B = '02:00:00:00:00:01', '02:00:00:00:00:02'


def rule(address=A, **changes):
    return dict(mac=address, name='Test device', group='', color='#3388FF', brightness=30,
                enabled=True, allow_shared=False, **changes)


def table(rows):
    header = 'port vlan mac-address       ip-address      hostname          uptime     age wireless-type\n'
    header += '---- ---- ----------------- --------------- ---------------- ------- ------- -------------\n'
    for port, address, name, age in rows:
        header += f'{port:4} {1:4} {address:17} {"192.0.2.10":15} {name:16} {1000:7} {age:7} {"":13}\n'
    return header + f'Total number of entries: {len(rows)}\n'


def port_table():
    return '\n'.join(f'{"U" if p==51 else ""}{p} U/U 1000F 0 0 0 0' for p in range(1, 53))


class FakeSwitch:
    writable = True
    def __init__(self):
        self.table = table([(12, A, 'Living Room', 10)])
        self.commands = []
    def read(self, name):
        return self.table if name == 'mac_table' else port_table()
    def verify_control(self): pass
    def color(self, port, color, brightness): self.commands.append(('color', port, color, brightness))
    def restore(self): self.commands.append(('restore',))


class CoreTests(unittest.TestCase):
    def test_empty_hostname_and_spaces(self):
        rows = parse_macs(table([(12,A,'Living Room',42),(15,B,'',2)]))
        self.assertEqual(rows[0]['name'],'Living Room')
        self.assertEqual(rows[1]['name'],'')
        self.assertEqual(rows[0]['age'],42)

    def test_uplink_and_incomplete_ports(self):
        self.assertTrue(parse_ports(port_table())[51]['uplink'])
        with self.assertRaises(ValueError): parse_ports('1 U/U 1000F')

    def test_refuse_unknown_mac_table(self):
        with self.assertRaises(ValueError): parse_macs('command error')

    def plan(self, rows, rules):
        return make_plan(parse_macs(table(rows)), parse_ports(port_table()), dict(version=1,rules=rules))

    def test_same_mac_multiple_vlans_is_one_location(self):
        plan=self.plan([(12,A,'TV',1),(12,A,'TV',1)],[rule()])
        self.assertEqual(set(plan['desired']),{12})

    def test_ambiguous_location_is_blocked(self):
        plan=self.plan([(12,A,'TV',1),(14,A,'TV',1)],[rule()])
        self.assertEqual(plan['desired'],{})

    def test_shared_and_uplink_blocked(self):
        for rows in [[(12,A,'TV',1),(12,B,'Other',1)],[(51,A,'Router',1)]]:
            self.assertEqual(self.plan(rows,[rule()])['desired'],{})

    def test_shared_conflicting_colors_blocked(self):
        r1=rule();r1['allow_shared']=True
        r2=rule(B);r2.update(allow_shared=True,color='#FF0000')
        self.assertEqual(self.plan([(12,A,'TV',1),(12,B,'Other',1)],[r1,r2])['desired'],{})

    def test_stale_and_paused_rule_not_applied(self):
        self.assertEqual(self.plan([(12,A,'TV',301)],[rule()])['desired'],{})
        r=rule();r['enabled']=False
        self.assertEqual(self.plan([(12,A,'TV',1)],[r])['desired'],{})

    def test_command_validation_blocks_injection_and_reset_modes(self):
        command=led_command(12,'#0066FF',30)
        self.assertEqual(command,"echo '12 w 0' > /proc/led/led_color && echo '12 r 0' > /proc/led/led_color && echo '12 g 7864' > /proc/led/led_color && echo '12 b 19660' > /proc/led/led_color")
        self.assertIn("12 r 65535",led_command(12,'#FF0000',100))
        for port,color,brightness in [(0,'#0066FF',30),(53,'#0066FF',30),(12,'#0066FF;reboot',30),(12,'#0066FF',0)]:
            with self.assertRaises(ValueError):led_command(port,color,brightness)
        with self.assertRaises(ValueError):restore_command(10)

    def test_duplicate_rules_and_bad_colors_rejected(self):
        with self.assertRaises(ValueError):validate_rules(dict(version=1,rules=[rule(),rule()]))
        r=rule();r['color']='blue'
        with self.assertRaises(ValueError):validate_rules(dict(version=1,rules=[r]))


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.switch=FakeSwitch()
        self.app=Application(Path(self.temp.name),{'allow_led_control':True},self.switch)
        self.app.action('/api/rules',dict(version=1,rules=[rule()]))
        self.app.refresh()
    def tearDown(self):self.temp.cleanup()

    def test_save_is_read_only_and_persistent(self):
        self.assertEqual(self.switch.commands,[])
        app=Application(Path(self.temp.name),{},self.switch)
        self.assertEqual(app.rules['rules'][0]['mac'],A)

    def test_preset_lifecycle_persists_without_changing_active_rules(self):
        self.app.action('/api/start',{})
        before=list(self.switch.commands)
        saved=json.loads(json.dumps(self.app.rules))
        self.app.action('/api/presets',dict(operation='add',name=' Consoles ',color='#12ab34'))
        self.app.action('/api/presets',dict(operation='edit',original_name='Consoles',name='Games',color='#ABCDEF'))
        restarted=Application(Path(self.temp.name),{},self.switch)
        self.assertIn(dict(name='Games',color='#ABCDEF'),restarted.presets)
        self.app.action('/api/presets',dict(operation='delete',original_name='Games'))
        for preset in list(self.app.presets):
            self.app.action('/api/presets',dict(operation='delete',original_name=preset['name']))
        self.assertEqual(Application(Path(self.temp.name),{},self.switch).presets,[])
        self.assertEqual(self.app.rules,saved)
        self.assertEqual(self.switch.commands,before)
        self.assertTrue(self.app.active)

    def test_invalid_presets_do_not_replace_saved_choices(self):
        before=self.app.presets.copy()
        for name,color in [(' cameras ','#123456'),('','#123456'),('x'*41,'#123456'),('Bad','red')]:
            with self.subTest(name=name,color=color),self.assertRaises(ValueError):
                self.app.action('/api/presets',dict(operation='add',name=name,color=color))
        with self.assertRaises(ValueError):
            self.app.action('/api/presets',dict(operation='delete',original_name='Missing'))
        self.assertEqual(self.app.presets,before)
        self.assertEqual(self.switch.commands,[])

    def test_start_is_disabled_by_default(self):
        self.app.allow_control=False
        with self.assertRaises(ValueError):self.app.action('/api/start',{})
        self.assertEqual(self.switch.commands,[])

    def test_fallback_covers_named_unassigned_shared_ports_but_not_reserved(self):
        self.switch.table=table([(12,A,'Assigned',1),(12,B,'Other',1),(15,B,'Named',1),
                                 (15,'02:00:00:00:00:03','Other',1),(51,B,'Router',1),
                                 (16,B,'Stale',301)])
        settings=dict(self.app.settings,fallback_enabled=True)
        self.app.action('/api/settings',settings)
        self.app.refresh()
        plan=self.app.plan()
        self.assertEqual(plan['fallback_ports'],[15])
        self.assertNotIn(12,plan['desired'])  # Explicit shared-port permission still required.
        saved=rule();saved.update(allow_shared=True)
        self.app.action('/api/rules',dict(version=1,rules=[saved]))
        self.assertEqual(self.app.plan()['desired'][12]['color'],'#3388FF')
        saved['enabled']=False
        self.app.action('/api/rules',dict(version=1,rules=[saved]))
        self.assertNotIn(12,self.app.plan()['desired'])

    def test_fallback_does_not_bypass_conflict_or_disconnected_port(self):
        self.switch.table=table([(12,A,'A',1),(12,B,'B',1),(15,B,'B',1)])
        self.app.refresh()
        self.app.ports[15]['up']=False
        one=rule();one['allow_shared']=True
        two=rule(B);two.update(allow_shared=True,color='#FF0000')
        plan=make_plan(self.app.rows,self.app.ports,dict(version=1,rules=[one,two]),
                       settings=dict(self.app.settings,fallback_enabled=True))
        self.assertEqual(plan['desired'],{})

    def test_unchanged_polls_skip_writes_manual_refresh_forces_them(self):
        self.app.action('/api/start',{})
        before=list(self.switch.commands)
        self.app.refresh()
        self.assertEqual(self.switch.commands,before)
        self.app.action('/api/refresh',{})
        self.assertEqual(self.switch.commands,before+before)
        self.app.action('/api/stop',{})
        before=list(self.switch.commands)
        self.app.action('/api/refresh',{})
        self.assertEqual(self.switch.commands,before)

    def test_scheduler_separate_intervals_and_changes_only(self):
        with patch('app.time.monotonic',return_value=100):
            self.app.action('/api/settings',dict(self.app.settings,poll_seconds=30,push_seconds=90))
            self.app.action('/api/start',{})
        before=list(self.switch.commands)
        with patch('app.time.monotonic',return_value=130):self.app.tick()
        self.assertEqual(self.switch.commands,before)
        with patch('app.time.monotonic',return_value=190):self.app.tick()
        self.assertEqual(self.switch.commands,before+before)
        with patch('app.time.monotonic',return_value=200):
            self.app.action('/api/settings',dict(self.app.settings,push_seconds=0))
        before=list(self.switch.commands)
        with patch('app.time.monotonic',return_value=900):self.app.tick()
        self.assertEqual(self.switch.commands,before)

    def test_settings_persist_and_invalid_settings_leave_control_running(self):
        self.app.action('/api/start',{})
        desired=dict(self.app.settings,poll_seconds=3600,push_seconds=0,fallback_enabled=True)
        self.app.action('/api/settings',desired)
        restarted=Application(Path(self.temp.name),{},self.switch)
        self.assertEqual(restarted.settings,desired)
        before=list(self.switch.commands)
        for key,value in [('poll_seconds',0),('push_seconds',1),('push_seconds',True),
                          ('fallback_color','white'),('fallback_brightness',101),('fallback_enabled','true')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.app.action('/api/settings',dict(desired,**{key:value}))
        self.assertEqual(self.app.settings,desired)
        self.assertTrue(self.app.active)
        self.assertEqual(self.switch.commands,before)

    def test_fallback_replaces_deleted_rule_and_rule_takes_precedence(self):
        self.app.action('/api/settings',dict(self.app.settings,fallback_enabled=True))
        self.app.action('/api/start',{})
        self.app.action('/api/rules',dict(version=1,rules=[]))
        self.assertEqual(self.switch.commands[-1],('color',12,'#FFFFFF',20))
        self.assertNotIn(('restore',),self.switch.commands)
        self.app.action('/api/rules',dict(version=1,rules=[rule()]))
        self.assertEqual(self.switch.commands[-1],('color',12,'#3388FF',30))

    def test_check_does_not_apply_changed_plan_while_active(self):
        self.app.action('/api/start',{})
        self.switch.table=table([(15,A,'Moved',1)])
        before=list(self.switch.commands)
        self.app.action('/api/check',{})
        self.assertEqual(self.switch.commands,before)

    def test_interface_check_does_not_write_leds(self):
        self.app.allow_control=False
        self.app.action('/api/check',{})
        self.assertEqual(self.switch.commands,[])

    def test_move_clears_old_port_before_new_color(self):
        self.app.action('/api/start',{})
        self.switch.table=table([(15,A,'Living Room',1)])
        self.app.refresh()
        self.assertEqual(self.switch.commands[-2:],[('restore',),('color',15,'#3388FF',30)])
        self.app.action('/api/stop',{})
        self.assertFalse(self.app.pending)
        self.assertFalse(self.app.active)

    def test_failure_stops_and_restores(self):
        self.app.action('/api/start',{})
        self.app.handle_failure(RuntimeError('Discovery failed'))
        self.assertFalse(self.app.active)
        self.assertFalse(self.app.pending)
        self.assertEqual(self.switch.commands[-1],('restore',))

    def test_failed_restore_keeps_recovery_marker(self):
        self.app.action('/api/start',{})
        def fail():raise OSError('disconnected')
        self.switch.restore=fail
        self.app.handle_failure(RuntimeError('Discovery failed'))
        self.assertTrue(self.app.marker.exists())
        self.assertFalse(self.app.active)

    def test_http_preview_csrf_and_host_checks(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app,True))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/state') as response:
                self.assertEqual(json.load(response)['rows'][0]['mac'],A)
            bad=Request(base+'/api/rules',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
            with self.assertRaises(HTTPError) as error:urlopen(bad)
            self.assertEqual(error.exception.code,403)
            bad=Request(base+'/',headers={'Host':'attacker.invalid'})
            with self.assertRaises(HTTPError) as error:urlopen(bad)
            self.assertEqual(error.exception.code,403)
            good=Request(base+'/api/rules',data=json.dumps(dict(version=1,rules=[rule()])).encode(),headers={'Content-Type':'application/json','X-Etherlighting-CSRF':self.app.csrf},method='POST')
            with urlopen(good) as response:self.assertEqual(response.status,200)
        finally:
            server.shutdown();server.server_close();worker.join()


class SwitchErrorTests(unittest.TestCase):
    def test_failure_details_survive_either_output_stream(self):
        for output_stream in ('stdout', 'stderr'):
            with self.subTest(output_stream=output_stream):
                channel=Mock()
                channel.recv_ready.side_effect=[output_stream=='stdout',False,False]
                channel.recv_stderr_ready.side_effect=[output_stream=='stderr',False,False]
                channel.recv.return_value=b'write rejected by device'
                channel.recv_stderr.return_value=b'write rejected by device'
                channel.exit_status_ready.return_value=True
                channel.recv_exit_status.return_value=1
                switch=SSHSwitch({})
                switch.client=Mock()
                switch.client.get_transport.return_value.is_active.return_value=True
                switch.client.get_transport.return_value.open_session.return_value=channel
                with self.assertRaisesRegex(RuntimeError,'exit 1.*write rejected by device'):
                    switch._run('fixed diagnostic command')
                channel.close.assert_called_once()


if __name__=='__main__':unittest.main()
