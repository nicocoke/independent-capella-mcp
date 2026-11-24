import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class PackageTests(unittest.TestCase):
    def test_python_sources_parse(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob("*.py"):
            with self.subTest(path=path.name): ast.parse(path.read_text(encoding="utf-8"))

    def test_native_descriptors_parse(self):
        root = Path(__file__).resolve().parents[1] / "native"
        paths = list(root.rglob("*.xml")) + list(root.rglob("*.target"))
        self.assertGreater(len(paths), 5)
        for path in paths:
            with self.subTest(path=path.name): ET.parse(path)

    def test_plugin_has_manual_activation_and_no_startup_extension(self):
        root = Path(__file__).resolve().parents[1] / "native/org.example.capella.mcp"
        plugin = ET.parse(root / "plugin.xml").getroot()
        points = {item.attrib["point"] for item in plugin.findall("extension")}
        self.assertIn("org.eclipse.ui.handlers", points)
        self.assertNotIn("org.eclipse.ui.startup", points)
        self.assertNotIn("Bundle-Activator:", (root / "META-INF/MANIFEST.MF").read_text())
        self.assertIn("Bundle-SymbolicName: org.example.capella.mcp;singleton:=true", (root / "META-INF/MANIFEST.MF").read_text())

    def test_runtime_harness_is_excluded_from_shipping_feature(self):
        root = Path(__file__).resolve().parents[1]
        feature = ET.parse(root / "native/feature/feature.xml").getroot()
        identifiers = {plugin.attrib["id"] for plugin in feature.findall("plugin")}
        self.assertNotIn("org.example.capella.mcp.tests", identifiers)
        self.assertIn("com.google.gson", identifiers)
        self.assertEqual({"org.example.capella.mcp", "com.google.gson"}, identifiers)
