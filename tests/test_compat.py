import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from compat.rule_generator import RuleGenerator

class TestCompatibility(unittest.TestCase):
    """Test code transformation and compatibility generation."""

    def setUp(self):
        self.generator = RuleGenerator()

    def test_variable_renaming(self):
        """Test that variables are renamed."""
        code = """
int main() {
    int counter = 0;
    DWORD processId = 123;
    return 0;
}
"""
        mutated = self.generator.rename_vars(code)
        # Check that code was modified
        self.assertNotEqual(code, mutated)
        # Original variable names should not appear unchanged
        # (Note: This is a basic test; actual variable renaming is probabilistic)

    def test_dead_code_insertion(self):
        """Test that dead code is inserted."""
        code = "int main() { return 0; }"
        mutated = self.generator.insert_deadcode(code)
        # Mutated code should be longer
        self.assertGreater(len(mutated), len(code))

    def test_string_encryption(self):
        """Test que strings are encrypted."""
        code = 'char* msg = "Hello World";'
        mutated = self.generator.encrypt_strings(code)
        # Should contain decryption stub
        self.assertIn("_decrypt_xor", mutated)
        # Original string should be transformed
        self.assertNotIn('"Hello World"', mutated)

if __name__ == '__main__':
    unittest.main()
