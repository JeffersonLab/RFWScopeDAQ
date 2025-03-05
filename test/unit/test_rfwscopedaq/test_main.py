"""Unit tests for functions in the main module"""
from unittest import TestCase
from rfwscopedaq.main import validate_zone, validate_cavity


class TestMain(TestCase):
    """Class for testing functions in the main module"""
    def test_validate_cavity1(self):
        """Test that all real cavity names are accepted"""
        for l in "12":
            for z in "23456789ABCDEFGHIJKLMNOPQ":
                for c in "12345678":
                    validate_cavity(f"R{l}{z}{c}")
        l = 0
        for z in '34':
            for c in "12345678":
                validate_cavity(f"R{l}{z}{c}")

        validate_cavity("R027")
        validate_cavity("R028")

    def test_validate_cavity2(self):
        """Test that an EPICS zone name is blocked"""
        with self.assertRaises(ValueError):
            validate_cavity("R1M")

    def test_validate_cavity3(self):
        """Test that a CED zone name is blocked"""
        with self.assertRaises(ValueError):
            validate_cavity("1L22")

    def test_validate_cavity4(self):
        """Test that a CED cavity name is blocked"""
        with self.assertRaises(ValueError):
            validate_cavity("1L22-1")

    def test_validate_cavity5(self):
        """Test that an all-around bad name is blocked"""
        with self.assertRaises(ValueError):
            validate_cavity("asdf")

    def test_validate_zone1(self):
        """Test that all real zone names are accepted"""
        for l in "12":
            for z in "23456789ABCDEFGHIJKLMNOPQ":
                validate_zone(f"R{l}{z}")
        l = 0
        for z in '234':
            validate_zone(f"R{l}{z}")

    def test_validate_zone2(self):
        """Test that an EPICS cavity name is blocked"""
        with self.assertRaises(ValueError):
            validate_zone("R1M1")

    def test_validate_zone3(self):
        """Test that a CED zone name is blocked"""
        with self.assertRaises(ValueError):
            validate_zone("1L22")

    def test_validate_zone4(self):
        """Test that a CED cavity name is blocked"""
        with self.assertRaises(ValueError):
            validate_zone("1L22-1")

    def test_validate_zone5(self):
        """Test that an all around bad name is blocked"""
        with self.assertRaises(ValueError):
            validate_zone("asdf")
