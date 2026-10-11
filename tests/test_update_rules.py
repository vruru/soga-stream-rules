import sys, unittest, yaml, json, os, tempfile
from pathlib import Path
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import update_rules as u

FIXTURE = '''\
# ---------- > Global Plaform
# > Netflix
"domain:global.test",
"domain:global.test",
# "domain:disabled.test",
# ---------- > Taiwan Media
# > Local
"domain:tw.test",
# ---------- > Japan Media
"domain:jp.test",
# ---------- > North America Media
"domain:us.test",
# ---------- > Korean Media
"domain:kr.test",
# ---------- > Indian Media
"domain:india-extra.test",
# ---------- > ? media
"domain:unknown-media.test",
# ---------- > SouthEastAsia media
# > HBO GO Asia
"domain:sea-common.test",
# > SG:meWATCH
"domain:sg.test",
# > CatchPlay+
"domain:sea-common-late.test",
# > TH:TrueID
"domain:th.test",
# > IN:Jio Cinema
"domain:in.test",
# > UAE:shahid
"domain:uae.test",
# ---------- > Europe Media
# > EU:Shared
"domain:eu-common.test",
# > ViaPlay
"domain:eu-common2.test",
# > IT Rai Play
"domain:it.test",
# > GB:BBC
"domain:gb.test",
# ---------- > Oceania Media
# > NBA TV
"domain:oc-common.test",
# > AU:Stan
"domain:au.test",
# > NZ:SkyGO
"domain:nz.test",
# > NZ:Maori TV
# ---------- > AI Platform
# > Openai
"domain:openai.test",
# > Claude 2 /HK Only/
"domain:claude.test",
# ---------- > Others
"domain:other.test",
# ---------- > China Media
"domain:china-only.test",
"domain:global.test",
malformed ignored China rule
# ---------- > Future
"domain:future.test",
'''

EXPECTED = {
    'TW': {'domain:global.test','domain:tw.test','domain:openai.test'},
    'JP': {'domain:global.test','domain:jp.test','domain:openai.test'},
    'US': {'domain:global.test','domain:us.test','domain:openai.test'},
    'KR': {'domain:global.test','domain:kr.test','domain:openai.test'},
    'SG': {'domain:global.test','domain:sea-common.test','domain:sea-common-late.test','domain:sg.test'},
    'TH': {'domain:global.test','domain:sea-common.test','domain:sea-common-late.test','domain:th.test'},
    'IN': {'domain:global.test','domain:sea-common.test','domain:sea-common-late.test','domain:in.test','domain:india-extra.test'},
    'UAE': {'domain:global.test','domain:sea-common.test','domain:sea-common-late.test','domain:uae.test'},
    'IT': {'domain:global.test','domain:eu-common.test','domain:eu-common2.test','domain:it.test','domain:openai.test'},
    'GB': {'domain:global.test','domain:eu-common.test','domain:eu-common2.test','domain:gb.test','domain:openai.test'},
    'AU': {'domain:global.test','domain:unknown-media.test','domain:oc-common.test','domain:au.test','domain:openai.test'},
    'NZ': {'domain:global.test','domain:unknown-media.test','domain:oc-common.test','domain:nz.test','domain:openai.test'},
    'HK': {'domain:global.test','domain:tw.test','domain:jp.test','domain:us.test','domain:kr.test',
           'domain:india-extra.test','domain:unknown-media.test','domain:sea-common.test','domain:sg.test',
           'domain:sea-common-late.test','domain:th.test','domain:in.test','domain:uae.test',
           'domain:eu-common.test','domain:eu-common2.test','domain:it.test','domain:gb.test',
           'domain:oc-common.test','domain:au.test','domain:nz.test','domain:openai.test',
           'domain:claude.test','domain:other.test','domain:future.test'},
}
ALL_CODES = set(EXPECTED)  # 13 codes


def _rules(outputs, code):
    return next(iter(yaml.safe_load(outputs[code + '.yml']).values()))['rules']


def _gen():
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        return u.generate(FIXTURE)


class TestUpdateRules(unittest.TestCase):

    def test_01_file_set(self):
        self.assertEqual(set(_gen().keys()), {c + '.yml' for c in ALL_CODES})

    def test_02_per_code_sets(self):
        out = _gen()
        for code, exp in EXPECTED.items():
            self.assertEqual(set(_rules(out, code)), exp, msg=code)

    def test_03_yaml_structure(self):
        for code in ALL_CODES:
            text = _gen()[code + '.yml']
            doc = yaml.safe_load(text)
            self.assertIsInstance(doc, dict)
            self.assertEqual(len(doc), 1)
            config = next(iter(doc.values()))
            self.assertEqual(config['strategy'], 'ipv4_first')
            rules = config['rules']
            self.assertIsInstance(rules, list)
            self.assertTrue(all(isinstance(item, str) for item in rules))
            self.assertEqual(len(rules), len(set(rules)))
            lines = text.splitlines()
            stripped_lines = [l.strip() for l in lines]
            self.assertIn('# ---------- > Global Plaform', stripped_lines)
            self.assertIn('# > Netflix', stripped_lines)
            forbidden = ['# generated', '# region:']
            for line in stripped_lines:
                for f in forbidden:
                    self.assertFalse(line.startswith(f), f"Forbidden header found: {f} in line: {line}")

    def test_04_crlf_and_idempotent(self):
        out_a = _gen()
        out_b = u.generate(FIXTURE.replace('\n', '\r\n'))
        for code in ALL_CODES:
            self.assertEqual(yaml.safe_load(out_a[code + '.yml']), yaml.safe_load(out_b[code + '.yml']))
        self.assertEqual(out_a, out_b)

    def test_05_china_and_comment_unchanged(self):
        mod = FIXTURE.replace('"domain:china-only.test"', '"domain:china-modified.test"')
        mod = mod.replace('# > Netflix', '# > Netflix\n# ordinary changed comment')
        out = _gen()
        out2 = u.generate(mod)
        self.assertEqual(set(_rules(out2, 'TW')), EXPECTED['TW'])
        self.assertEqual(out, out2)

    def test_06_value_errors(self):
        cases = [
            FIXTURE.replace('# ---------- > Taiwan Media', '# ---------- > Japan Media'),
            '{bad json',
            FIXTURE.replace('"domain:tw.test"', '"domain:"'),
            FIXTURE.replace('# > SG:meWATCH', '# > ZZ:Unknown'),
            FIXTURE + '# ---------- > Taiwan Media\n"domain:dup.test",\n',
            FIXTURE.replace('# > Claude 2 /HK Only/', '# > Openai\n"domain:dup2.test",\n# > Claude 2 /HK Only/'),
        ]
        for inp in cases:
            with self.assertRaises(ValueError, msg=inp[:40]):
                u.generate(inp)

    def test_07_new_es_file(self):
        mod = FIXTURE.replace(
            '# ---------- > Oceania Media',
            '# > ES:New\n"domain:es.test",\n# ---------- > Oceania Media')
        out = _gen()
        out2 = u.generate(mod)
        self.assertIn('ES.yml', out2)
        self.assertIn('domain:es.test', _rules(out2, 'ES'))

    def test_08_rule_strings_roundtrip(self):
        extra_rules = [
            r'regexp:^example\.test/(foo|bar)$',
            'keyword:quoted "name"',
            'full:exact.example.test'
        ]
        # Construct source fixture with extra rules inserted after jp.test
        insertion = '\n' + '\n'.join(json.dumps(rule) + ',' for rule in extra_rules)
        source = FIXTURE.replace('"domain:jp.test",', '"domain:jp.test",' + insertion)

        result = u.generate(source)
        jp_yml = result['JP.yml']
        rules = _rules(result, 'JP')

        for rule in extra_rules:
            self.assertIn(rule, rules)

        # Assert comments retained (checking global lines in JP file for safety, assuming structure preserved)
        stripped_lines = [l.strip() for l in jp_yml.splitlines()]
        self.assertIn('# ---------- > Global Plaform', stripped_lines)
        self.assertIn('# > Netflix', stripped_lines)

    def test_09_update_files(self):
        out = _gen()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            changed = u.update_files(out, d)
            self.assertEqual(set(changed), set(out))
            mtimes = {f: (d / f).stat().st_mtime for f in out}
            changed2 = u.update_files(out, d)
            self.assertEqual(changed2, [])
            for f in out:
                self.assertEqual((d / f).stat().st_mtime, mtimes[f])
            d2 = Path(td) / 'newsub'
            res = u.update_files(out, d2, check=True)
            self.assertEqual(set(res), set(out))
            self.assertFalse(d2.exists())
            stale = out['TW.yml'].replace('domain:tw.test', 'domain:stale-tw.test')
            (d / 'TW.yml').write_text(stale)
            res2 = u.update_files(out, d, check=True)
            self.assertIn('TW.yml', res2)
            self.assertEqual((d / 'TW.yml').read_text(), stale)

    def test_10_old_zz_rejected(self):
        out = _gen()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            u.update_files(out, d)
            (d / 'ZZ.yml').write_text('old\n')
            before = {f: (d / f).read_bytes() for f in out}
            with self.assertRaises(ValueError):
                u.update_files(out, d)
            for f in out:
                self.assertEqual((d / f).read_bytes(), before[f])

    def test_11_symlink_rejected(self):
        out = _gen()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / 'TW.yml').write_text('x\n')
            (d / 'target.txt').write_text('keep\n')
            (d / 'TW.yml').unlink()
            (d / 'TW.yml').symlink_to(d / 'target.txt')
            with self.assertRaises(ValueError):
                u.update_files(out, d)
            self.assertEqual((d / 'target.txt').read_text(), 'keep\n')

    def test_12_main_network_fail(self):
        out = _gen()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            u.update_files(out, d)
            before = {f: (d / f).read_bytes() for f in out}
            with patch('urllib.request.urlopen', side_effect=OSError('network down')):
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    rc = u.main(['--output-dir', str(d)])
            self.assertEqual(rc, 2)
            for f in out:
                self.assertEqual((d / f).read_bytes(), before[f])

    def test_13_main_bad_json_source(self):
        out = _gen()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            u.update_files(out, d)
            src = d / 'src.json'
            src.write_text('{bad')
            before = {f: (d / f).read_bytes() for f in out}
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                rc = u.main(['--source-file', str(src), '--output-dir', str(d)])
            self.assertEqual(rc, 2)
            for f in out:
                self.assertEqual((d / f).read_bytes(), before[f])

    def test_14_main_check_flow(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            out = _gen()
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                rc = u.main(['--check', '--source-file', str(self._write(d)), '--output-dir', str(d)])
            self.assertEqual(rc, 1)
            self.assertFalse((d / 'TW.yml').exists())
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                rc2 = u.main(['--source-file', str(d / 'src'), '--output-dir', str(d)])
            self.assertEqual(rc2, 0)
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                rc3 = u.main(['--check', '--source-file', str(d / 'src'), '--output-dir', str(d)])
            self.assertEqual(rc3, 0)

    def test_15_cross_region_collision(self):
        source = FIXTURE.replace('# > SG:meWATCH', '# > GB:Collision')
        with self.assertRaises(ValueError):
            u.generate(source)

    def test_17_ambiguous_space_prefix_is_rejected(self):
        source = FIXTURE.replace('# > ViaPlay', '# > TV 2 Play')
        with self.assertRaises(ValueError):
            u.generate(source)

    def test_16_stage_failure_preserves_existing_files(self):
        outputs = _gen()
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            u.update_files(outputs, directory)
            before = {name: (directory / name).read_bytes() for name in outputs}
            modified = {name: text + '    # changed\n' for name, text in outputs.items()}
            real_tempfile = u.tempfile.NamedTemporaryFile
            calls = 0

            def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated disk failure')
                return real_tempfile(*args, **kwargs)

            with patch.object(u.tempfile, 'NamedTemporaryFile', side_effect=fail_second):
                with self.assertRaises(OSError):
                    u.update_files(modified, directory)
            self.assertEqual(before, {name: (directory / name).read_bytes() for name in outputs})
            self.assertFalse(list(directory.glob('.*.tmp')))

    def test_18_default_headers_and_legacy_migration(self):
        outputs = _gen()
        addresses = {
            'HK': 'tcp://hkg.core.access.zznet.fun',
            'JP': 'tcp://nrt.core.access.zznet.fun',
            'SG': 'tcp://sin2.edge.access.zznet.fun',
            'US': 'tcp://lax.core.access.zznet.fun',
        }
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            for name, text in outputs.items():
                code = name[:-4]
                doc = yaml.safe_load(text)
                self.assertEqual(list(doc), [addresses.get(code, 'tcp://example.com')])
                self.assertEqual(next(iter(doc.values()))['strategy'], 'ipv4_first')
                _, body = u.split_dns_document(text)
                legacy = ''.join(line[4:] for line in body.splitlines(keepends=True))
                (directory / name).write_bytes(legacy.encode())
            self.assertEqual(u.update_files(outputs, directory), sorted(outputs))
            self.assertEqual(u.update_files(outputs, directory), [])
            for name, text in outputs.items():
                self.assertEqual((directory / name).read_bytes(), text.encode())

    def test_19_manual_header_survives_rule_update(self):
        outputs = _gen()
        custom = ('# custom header\r\n'
                  'tcp://custom.example.net:5353:\r\n'
                  '  strategy: ipv6_first # manual\r\n'
                  '  timeout: 15 # additional scalar\r\n'
                  '  rules: # keep marker\r\n').encode()
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            u.update_files(outputs, directory)
            _, body = u.split_dns_document(outputs['JP.yml'])
            (directory / 'JP.yml').write_bytes(custom + body.encode())
            before = {name: (directory / name).read_bytes() for name in outputs}
            self.assertEqual(u.update_files(outputs, directory), [])
            changed = u.generate(FIXTURE.replace('jp.test', 'updated-jp.test'))
            self.assertEqual(u.update_files(changed, directory), ['HK.yml', 'JP.yml'])
            final = (directory / 'JP.yml').read_bytes()
            self.assertEqual(u.split_dns_document(final.decode())[0].encode(), custom)
            rules = next(iter(yaml.safe_load(final).values()))['rules']
            self.assertIn('domain:updated-jp.test', rules)
            self.assertNotIn('domain:jp.test', rules)
            for name in outputs.keys() - {'HK.yml', 'JP.yml'}:
                self.assertEqual((directory / name).read_bytes(), before[name])
            self.assertEqual(u.update_files(changed, directory), [])

    def test_20_invalid_documents_abort_batch_before_write(self):
        header = 'tcp://custom.example.net:\n  strategy: ipv4_first\n  rules:\n'
        bad = [
            b'\xff', b'# only comments\n', b'',
            header.replace('  rules:\n', '').encode(),
            (header + '  rules:\n').encode(),
            ('tcp://second.example.net:\n' + header).encode(),
            header.replace('ipv4_first', '"unclosed').encode(),
            header.replace('ipv4_first', '"bad\\q"').encode(),
            header.replace('ipv4_first', '[ipv4_first]').encode(),
            header.replace('  strategy: ipv4_first\n', '').encode(),
            header.replace('  rules:', '  rules: []').encode(),
            (header + '  - "domain:bad.test"\n').encode(),
            (header + '    - "unsupported:bad.test"\n').encode(),
            (header + '    - "domain:"\n').encode(),
            b'- "domain:"\n', b'- "domain:a.test"\nmalformed\n',
        ]
        outputs = _gen()
        changed = u.generate(FIXTURE.replace('global.test', 'newglobal.test'))
        for invalid in bad:
            with self.subTest(invalid=repr(invalid)):
                with tempfile.TemporaryDirectory() as td:
                    directory = Path(td)
                    u.update_files(outputs, directory)
                    (directory / 'JP.yml').write_bytes(invalid)
                    before = {name: ((directory / name).read_bytes(),
                                     (directory / name).stat().st_mtime_ns)
                              for name in outputs}
                    with self.assertRaises((ValueError, UnicodeError)):
                        u.update_files(changed, directory)
                    for name, (content, mtime) in before.items():
                        self.assertEqual((directory / name).read_bytes(), content)
                        self.assertEqual((directory / name).stat().st_mtime_ns, mtime)
                    self.assertFalse(list(directory.glob('.*.tmp')))

    def test_21_check_mode_keeps_manual_header(self):
        outputs = _gen()
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            u.update_files(outputs, directory)
            _, body = u.split_dns_document(outputs['JP.yml'])
            custom = '# manual\n"tcp://custom.example.net:53":\n  strategy: ipv6_only\n  rules:\n'
            (directory / 'JP.yml').write_bytes((custom + body).encode())
            before = {name: (directory / name).read_bytes() for name in outputs}
            self.assertEqual(u.update_files(outputs, directory, check=True), [])
            changed = u.generate(FIXTURE.replace('jp.test', 'updated-jp.test'))
            self.assertEqual(u.update_files(changed, directory, check=True), ['HK.yml', 'JP.yml'])
            self.assertEqual(before, {name: (directory / name).read_bytes() for name in outputs})

    def test_22_new_country_and_manual_header(self):
        outputs = _gen()
        source = FIXTURE.replace('# ---------- > Oceania Media',
                                 '# > ES:New\n"domain:es.test",\n# ---------- > Oceania Media')
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            u.update_files(outputs, directory)
            custom = outputs['JP.yml'].replace('tcp://nrt.core.access.zznet.fun',
                                               'tcp://custom.example.net')
            (directory / 'JP.yml').write_bytes(custom.encode())
            self.assertEqual(u.update_files(u.generate(source), directory), ['ES.yml', 'HK.yml'])
            self.assertEqual((directory / 'JP.yml').read_bytes(), custom.encode())
            doc = yaml.safe_load((directory / 'ES.yml').read_bytes())
            self.assertEqual(list(doc), ['tcp://example.com'])
            self.assertEqual(doc['tcp://example.com']['strategy'], 'ipv4_first')
            self.assertIn('domain:es.test', doc['tcp://example.com']['rules'])

    def test_23_supported_header_forms(self):
        generated = _gen()['JP.yml']
        for uri in ['tcp://custom.example.net:53:', '"tcp://custom.example.net:53":',
                    "'tcp://custom.example.net:53':"]:
            for strategy in ['ipv6_first', '"ipv6_first"', "'ipv6_first'"]:
                custom = f'{uri} # upstream\n  strategy: {strategy}\n  rules: # manual\n'
                result = u.preserve_header(generated, custom.encode()).decode()
                self.assertTrue(result.startswith(custom))
                self.assertEqual(next(iter(yaml.safe_load(result).values()))['strategy'], 'ipv6_first')

    @staticmethod
    def _write(d):
        p = d / 'src'
        p.write_text(FIXTURE)
        return p


if __name__ == '__main__':
    unittest.main()
