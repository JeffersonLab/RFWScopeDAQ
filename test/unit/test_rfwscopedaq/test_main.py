from unittest import TestCase
from rfwscopedaq.main import validate_zone, validate_cavity

class TestMain(TestCase):

    def test_validate_cavity1(self):
        for l in "12":
            for z in "23456789ABCDEFGHIJKLMNOPQ":
                for c in "12345678":
                    validate_cavity(f"R{l}{z}{c}")
        l = 0
        for z in '34':
            for c in "12345678":
                validate_cavity(f"R{l}{z}{c}")

        validate_cavity(f"R027")
        validate_cavity(f"R028")

    def test_validate_cavity2(self):
        with self.assertRaises(ValueError):
            validate_cavity("R1M")

    def test_validate_cavity3(self):
        with self.assertRaises(ValueError):
            validate_cavity("1L22")

    def test_validate_cavity4(self):
        with self.assertRaises(ValueError):
            validate_cavity("1L22-1")

    def test_validate_cavity5(self):
        with self.assertRaises(ValueError):
            validate_cavity("asdf")

    def test_validate_zone1(self):
        for l in "12":
            for z in "23456789ABCDEFGHIJKLMNOPQ":
                    validate_zone(f"R{l}{z}")
        l = 0
        for z in '234':
            validate_zone(f"R{l}{z}")


    def test_validate_zone2(self):
        with self.assertRaises(ValueError):
            validate_zone("R1M1")

    def test_validate_zone3(self):
        with self.assertRaises(ValueError):
            validate_zone("1L22")

    def test_validate_zone4(self):
        with self.assertRaises(ValueError):
            validate_zone("1L22-1")

    def test_validate_zone5(self):
        with self.assertRaises(ValueError):
            validate_zone("asdf")