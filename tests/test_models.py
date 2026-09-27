import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from test_app import FakeSwitch, table, A, rule
from app import Application
from core import parse_ports, parse_macs, led_command
from models import PROFILES, identify, validate_interface
from switch import SSHSwitch

LED_HELP = 'Set port[1-52] LED: 1 ff cc ff 100'
RAW_HELP = 'Set port[1-52] LED color[r=Red g=Green b=Blue w=White] value[0-65535]; 1 r 65535'


def identity(model, firmware='US2.7.5.15'):
    return f'board.name={model}\n{firmware}\n'


class ModelTests(unittest.TestCase):
    def test_every_profile_discovers_complete_layout_and_rejects_out_of_range(self):
        for name, profile in PROFILES.items():
            with self.subTest(model=name):
                device=identify(identity(name))
                count=profile['port_count']
                text='\n'.join(f'{"U" if p==count else ""}{p} U/U 1000F' for p in range(1,count+1))
                self.assertEqual(len(parse_ports(text,count)),count)
                self.assertEqual(len(parse_macs(table([(count,A,'Device',1)]),count)),1)
                for broken in (text.rsplit('\n',1)[0],text+'\n1 U/U 1000F',text+f'\n{count+1} U/U 1000F'):
                    with self.assertRaises(ValueError):parse_ports(broken,count)
                with self.assertRaises(ValueError):parse_macs(table([(count+1,A,'Device',1)]),count)
                with self.assertRaises(ValueError):led_command(count+1,'#FFFFFF',20,count)
                self.assertIn(f"{count} w 0",led_command(count,'#FFFFFF',20,count))
                self.assertEqual(device['verified'],name=='USW-Pro-Max-48-PoE')

    def test_experimental_is_required_for_other_models_and_firmware(self):
        for name in PROFILES:
            device=identify(identity(name,'US7.4.1'))
            with self.assertRaisesRegex(ValueError,'experimental'):
                validate_interface(device,LED_HELP,RAW_HELP,'0')
            validate_interface(device,LED_HELP,RAW_HELP,'0',experimental=True)
        validate_interface(identify(identity('USW-Pro-Max-48-PoE')),LED_HELP,RAW_HELP,'0')

    def test_incompatible_interfaces_and_modes_are_blocked_even_with_opt_in(self):
        device=identify(identity('USW-Pro-Max-24-PoE'))
        for led,raw,mode in [(LED_HELP,RAW_HELP.replace('w=White',''),'0'),
                              (LED_HELP,RAW_HELP.replace('0-65535','0-255'),'0'),
                              (LED_HELP.replace('1-52','1-18'),RAW_HELP,'0'),
                              (LED_HELP,RAW_HELP,'3'),(LED_HELP,RAW_HELP,'0; reboot')]:
            with self.assertRaises(ValueError):validate_interface(device,led,raw,mode,True)

    def test_unknown_or_ambiguous_identity_is_blocked(self):
        for value in [identity('USW-Pro-XG-8-PoE'),identity('USW-48'),
                      'board.name=USW-Pro-Max-48-PoE\n',
                      identity('USW-Pro-Max-48-PoE')+'board.name=USW-Pro-Max-24\n']:
            with self.assertRaises(ValueError):identify(value)

    def test_each_profile_flows_through_app_discovery_and_color_plan(self):
        for name,profile in PROFILES.items():
            with self.subTest(model=name),tempfile.TemporaryDirectory() as directory:
                switch=FakeSwitch()
                switch.describe=lambda:identify(identity(name))
                switch.read=lambda key: table([(12,A,'Sample',1)]) if key=='mac_table' else '\n'.join(f'{p} U/U 1000F' for p in range(1,profile['port_count']+1))
                app=Application(Path(directory),{'allow_led_control':True},switch)
                app.action('/api/rules',dict(version=1,rules=[rule()]))
                app.action('/api/start',{})
                self.assertEqual(len(app.snapshot()['ports']),profile['port_count'])
                self.assertEqual(app.snapshot()['device']['model'],name)
                self.assertEqual(switch.commands[-1],('color',12,'#3388FF',30))

    def test_driver_gate_and_port_bounds_precede_writes(self):
        switch=SSHSwitch({})
        responses=dict(identity=identity('USW-Pro-Max-16'),led_help=LED_HELP,raw_help=RAW_HELP,mode='0')
        switch.read=Mock(side_effect=lambda key:responses[key])
        switch._run=Mock()
        with self.assertRaises(ValueError):switch.color(1,'#FFFFFF',20)
        switch._run.assert_not_called()
        switch.options['allow_experimental_models']=True
        switch.color(18,'#FFFFFF',20)
        self.assertIn('18 w 0',switch._run.call_args.args[0])
        before=switch._run.call_count
        with self.assertRaisesRegex(RuntimeError,'Unsupported port'):switch.color(19,'#FFFFFF',20)
        self.assertEqual(switch._run.call_count,before)
        responses['identity']=identity('USW-Pro-Max-24')
        with self.assertRaisesRegex(ValueError,'changed'):switch.verify_control()
        self.assertEqual(switch._run.call_count,before)


if __name__=='__main__':unittest.main()
