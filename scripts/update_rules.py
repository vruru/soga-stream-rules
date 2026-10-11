#!/usr/bin/env python3
"""update_rules.py - Parse 1stream xray rules and generate region YAML files."""

import sys
import os
import re
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error
import tempfile
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/1-stream/1stream-public-utils/"
    "refs/heads/main/stream.xray.list"
)
DEFAULT_DNS = "https://example.com/dns-query"
MAX_BYTES = 2 * 1024 * 1024 + 1

ISO_2 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ "
    "BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR "
    "CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR "
    "GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU "
    "ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ "
    "LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ "
    "MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF "
    "PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI "
    "SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR "
    "TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW".split()
)
COLON_ALLOWED = ISO_2 | frozenset({"UAE"})
SPACE_COUNTRIES = frozenset({"IT"})

REQUIRED_SECTIONS = (
    "Global Plaform",
    "Taiwan Media",
    "Japan Media",
    "North America Media",
    "Korean Media",
    "SouthEastAsia media",
    "Indian Media",
    "Europe Media",
    "Oceania Media",
    "? media",
    "AI Platform",
    "China Media",
)

VALID_PREFIXES = frozenset({"domain", "full", "regexp", "keyword"})

COUNTRY_RE = re.compile(r"^([A-Z]{2,3})(?::|\s+)")

SEC_HEAD_RE = re.compile(r"^#\s*-{5,}\s*>\s+(.+)$")
SEC_ANOMALY_RE = re.compile(r"^#\s*-{5,}")
SUB_RE = re.compile(r"^#\s*>\s+(.+)$")
FILENAME_RE = re.compile(r"^[A-Z]{2,3}\.yml$")


def _validate_dns(dns_server: str) -> None:
    if any(c.isspace() for c in dns_server):
        raise ValueError("dns_server must not contain whitespace")
    if "?" in dns_server:
        raise ValueError("dns_server must not contain query (?)")
    if "#" in dns_server:
        raise ValueError("dns_server must not contain fragment (#)")
    parsed = urllib.parse.urlparse(dns_server)
    if parsed.scheme != "https":
        raise ValueError("dns_server must be an HTTPS URL")
    if not parsed.hostname:
        raise ValueError("dns_server hostname must be non-empty")
    if parsed.username is not None:
        raise ValueError("dns_server must not contain username")
    if parsed.password is not None:
        raise ValueError("dns_server must not contain password")
    _ = parsed.port  # Validate explicit port if supplied.
    if parsed.query:
        raise ValueError("dns_server must not contain query")
    if parsed.fragment:
        raise ValueError("dns_server must not contain fragment")


def parse_source(text: str) -> list[dict]:
    blocks: list[dict] = []
    cur_section: str | None = None
    cur_title: str = ""
    cur_rules: list[str] = []
    seen_sections: set[str] = set()

    def flush() -> None:
        nonlocal cur_rules
        if cur_section is not None:
            blocks.append(
                {"section": cur_section, "title": cur_title, "rules": cur_rules[:]}
            )
        cur_rules = []

    for raw_line in text.split("\n"):
        line = raw_line.rstrip("\r")
        stripped = line.strip()

        if not stripped:
            continue

        # Section header
        m = SEC_HEAD_RE.match(stripped)
        if m:
            sec_name = m.group(1).strip()
            if cur_section is not None:
                flush()
            if sec_name in seen_sections:
                raise ValueError(f"duplicate section: {sec_name!r}")
            seen_sections.add(sec_name)
            cur_section = sec_name
            cur_title = ""
            continue

        # Anomaly: bare ---------- without >
        if SEC_ANOMALY_RE.match(stripped):
            raise ValueError(f"section header anomaly: {stripped!r}")

        if cur_section == "China Media":
            continue

        if re.match(r"^#\s*>\s*$", stripped):
            raise ValueError("empty subgroup title")

        # Subgroup title
        m2 = SUB_RE.match(stripped)
        if m2:
            if cur_section is None:
                raise ValueError("subgroup without section")
            flush()
            cur_title = m2.group(1).strip()
            continue

        # Commented-out rule
        if stripped.startswith("#"):
            continue

        # Active rule: parse as JSON
        # Check for malformed trailing commas
        temp_line = stripped
        if temp_line.endswith(","):
            temp_line = temp_line[:-1]
            if temp_line.endswith(","):
                raise ValueError("multiple trailing commas in rule")

        try:
            rule_val = json.loads(temp_line)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON rule: {stripped!r} ({e})")

        if not isinstance(rule_val, str):
            raise ValueError(f"rule must be a string: {stripped!r}")

        if not rule_val:
            raise ValueError("rule payload must not be empty")

        colon_pos = rule_val.find(":")
        if colon_pos < 0:
            raise ValueError(f"rule missing prefix: {rule_val!r}")
        prefix = rule_val[:colon_pos]
        if prefix not in VALID_PREFIXES:
            raise ValueError(f"unknown rule prefix: {prefix!r}")

        payload = rule_val[colon_pos+1:]
        if not payload:
            raise ValueError("rule payload must not be empty")

        if cur_section is None:
            raise ValueError(f"rule without section: {stripped!r}")

        cur_rules.append(rule_val)

    flush()

    # Validate required sections
    for req in REQUIRED_SECTIONS:
        if req not in seen_sections:
            raise ValueError(f"missing required section: {req!r}")

    # Validate active rules in required sections (China Media exempt)
    section_rules: dict[str, int] = {}
    for b in blocks:
        section_rules[b["section"]] = section_rules.get(b["section"], 0) + len(b["rules"])
    for req in REQUIRED_SECTIONS:
        if req == "China Media":
            continue
        if section_rules.get(req, 0) == 0:
            raise ValueError(f"required section has no active rules: {req!r}")

    # AI Platform: exactly one non-empty Openai subgroup
    ai_blocks = [b for b in blocks if b["section"] == "AI Platform"]
    openai_blocks = [b for b in ai_blocks if b["title"].casefold() == "openai"]
    non_empty_openai = [b for b in openai_blocks if b["rules"]]
    if len(openai_blocks) != 1 or len(non_empty_openai) != 1:
        raise ValueError(
            f"AI Platform must have exactly one non-empty Openai subgroup, got {len(non_empty_openai)}"
        )

    return blocks


def _country_from_title(title: str) -> tuple[str | None, str | None]:
    """Return (country_code_or_shared, cleaned_service_name).
    country_code: 2-letter ISO or UAE for country-specific; 'EU' for shared colon; None for no prefix.
    """
    m = COUNTRY_RE.match(title)
    if not m:
        return (None, title)
    prefix = m.group(1)
    rest = title[m.end():]
    sep_char = ":" if m.group(0)[-1] == ":" else " "

    if sep_char == ":":
        if prefix == "EU":
            return ("__SHARED__", rest)
        if prefix in COLON_ALLOWED:
            return (prefix, rest)
        raise ValueError(f"unknown country prefix (colon): {prefix!r} in title {title!r}")
    else:
        # Space form: must be exactly 2 chars to be a country
        if len(prefix) != 2:
            # 3-letter like NBA, HBO → not a country
            return (None, title)
        if prefix in SPACE_COUNTRIES:
            return (prefix, rest)
        raise ValueError(f"unknown country prefix (space): {prefix!r} in title {title!r}")


def build_regions(blocks: list[dict]) -> dict[str, list[dict]]:
    """Return {region_code: [blocks_in_order]}."""
    # Filter out China Media entirely
    work = [b for b in blocks if b["section"] != "China Media"]

    # Categorize blocks
    global_blocks = [b for b in work if b["section"] == "Global Plaform"]
    tw_blocks = [b for b in work if b["section"] == "Taiwan Media"]
    jp_blocks = [b for b in work if b["section"] == "Japan Media"]
    na_blocks = [b for b in work if b["section"] == "North America Media"]
    kr_blocks = [b for b in work if b["section"] == "Korean Media"]
    sea_blocks = [b for b in work if b["section"] == "SouthEastAsia media"]
    in_blocks = [b for b in work if b["section"] == "Indian Media"]
    eu_blocks = [b for b in work if b["section"] == "Europe Media"]
    oc_blocks = [b for b in work if b["section"] == "Oceania Media"]
    qm_blocks = [b for b in work if b["section"] == "? media"]
    ai_blocks = [b for b in work if b["section"] == "AI Platform"]

    ai_openai = [b for b in ai_blocks if b["title"].casefold() == "openai" and b["rules"]]

    # Parse country prefixes for multi-country sections
    def split_country(blks: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
        shared: list[dict] = []
        countries: dict[str, list[dict]] = {}
        for b in blks:
            cc, cleaned = _country_from_title(b["title"])
            if cc is None:
                shared.append(b)
            elif cc == "__SHARED__":
                if b["section"] != "Europe Media":
                    raise ValueError("EU shared prefix is only valid in Europe Media")
                shared.append(b)
            else:
                countries.setdefault(cc, []).append(b)
        return shared, countries

    sea_shared, sea_countries = split_country(sea_blocks)
    eu_shared, eu_countries = split_country(eu_blocks)
    oc_shared, oc_countries = split_country(oc_blocks)

    regions: dict[str, list[dict]] = {}

    # HK: all non-China blocks
    regions["HK"] = work[:]

    # TW, JP, US, KR: Global + section + AI(Openai)
    regions["TW"] = global_blocks + tw_blocks + ai_openai
    regions["JP"] = global_blocks + jp_blocks + ai_openai
    regions["US"] = global_blocks + na_blocks + ai_openai
    regions["KR"] = global_blocks + kr_blocks + ai_openai

    # Helper to check for collision
    def add_region(code: str, blks: list[dict]):
        if code in regions:
            raise ValueError(f"region code collision: {code}")
        regions[code] = blks

    # SEA countries: iterate sorted keys
    # Correction 3: Multi-country section needs >=1 country with rules
    has_sea_rules = any(any(b["rules"] for b in blks) for blks in sea_countries.values())
    if not has_sea_rules:
        raise ValueError("SouthEastAsia media section must have at least one country with rules")

    for cc in sorted(sea_countries.keys()):
        country_blks = sea_countries[cc]
        if not any(b["rules"] for b in country_blks):
            continue
        combined = global_blocks + sea_shared + country_blks
        if cc == "IN":
            combined = combined + in_blocks
        add_region(cc, combined)

    # Europe countries: iterate sorted keys
    has_eu_rules = any(any(b["rules"] for b in blks) for blks in eu_countries.values())
    if not has_eu_rules:
        raise ValueError("Europe Media section must have at least one country with rules")

    for cc in sorted(eu_countries.keys()):
        country_blks = eu_countries[cc]
        if not any(b["rules"] for b in country_blks):
            continue
        add_region(cc, global_blocks + eu_shared + country_blks + ai_openai)

    # Oceania countries: iterate sorted keys
    has_oc_rules = any(any(b["rules"] for b in blks) for blks in oc_countries.values())
    if not has_oc_rules:
        raise ValueError("Oceania Media section must have at least one country with rules")

    for cc in sorted(oc_countries.keys()):
        country_blks = oc_countries[cc]
        if not any(b["rules"] for b in country_blks):
            continue
        add_region(cc, global_blocks + qm_blocks + oc_shared + country_blks + ai_openai)

    return regions


def render_yaml(code: str, blocks: list[dict], dns_server: str) -> str:
    _validate_dns(dns_server)
    lines: list[str] = []
    lines.append("# generated")
    lines.append(f"# region: {code}")
    lines.append(f"{json.dumps(dns_server)}:")
    lines.append("  strategy: ipv4_only")
    lines.append("  rules:")

    seen: set[str] = set()
    prev_section = None

    for b in blocks:
        # Dedup one rule at a time, adding to seen immediately
        b_rules = []
        for r in b["rules"]:
            if r not in seen:
                seen.add(r)
                b_rules.append(r)

        if not b_rules:
            continue

        # Emit section heading only when changed
        if b["section"] != prev_section:
            lines.append(f"    # ---------- > {b['section']}")
            prev_section = b["section"]

        # Emit title comment
        if b["title"]:
            lines.append(f"    # > {b['title']}")

        for r in b_rules:
            lines.append(f"    - {json.dumps(r)}")

    return "\n".join(lines) + "\n"


def generate(text: str, dns_server: str = DEFAULT_DNS) -> dict[str, str]:
    _validate_dns(dns_server)
    blocks = parse_source(text)
    regions = build_regions(blocks)
    outputs: dict[str, str] = {}
    for code in sorted(regions.keys()):
        filename = f"{code}.yml"
        outputs[filename] = render_yaml(code, regions[code], dns_server)
    return outputs


def update_files(
    outputs: dict[str, str], output_dir: Path, check: bool = False,
) -> list[str]:
    """Validate the whole batch, stage it, then atomically replace each file."""
    if output_dir.is_symlink():
        raise ValueError(f"output directory must not be a symlink: {output_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"output directory is not a directory: {output_dir}")
    for name in outputs:
        if not FILENAME_RE.fullmatch(name):
            raise ValueError(f"invalid output filename: {name!r}")
    if output_dir.is_dir():
        obsolete = [
            entry.name for entry in output_dir.iterdir()
            if FILENAME_RE.fullmatch(entry.name) and entry.name not in outputs
        ]
        if obsolete:
            raise ValueError(
                "published countries disappeared; review before removing: "
                + ", ".join(sorted(obsolete))
            )

    changed = []
    for name in sorted(outputs):
        target = output_dir / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError(f"output target is not a regular file: {target}")
        expected = outputs[name].encode("utf-8")
        if not target.exists() or target.read_bytes() != expected:
            changed.append(name)
    if check or not changed:
        return changed

    output_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for name in changed:
            with tempfile.NamedTemporaryFile(
                dir=output_dir, prefix=".", suffix=".tmp", delete=False,
                mode="wb",
            ) as handle:
                temp_path = Path(handle.name)
                staged.append((temp_path, output_dir / name))
                handle.write(outputs[name].encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.chmod(0o644)
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return changed


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "update-rules/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read(MAX_BYTES)
    if len(data) >= MAX_BYTES:
        raise ValueError("source exceeds 2 MiB limit")
    return data.decode("utf-8-sig")


def _read_local(path: str) -> str:
    p = Path(path)
    size = p.stat().st_size
    if size >= MAX_BYTES:
        raise ValueError("source file exceeds 2 MiB limit")
    with open(p, "rb") as f:
        data = f.read(MAX_BYTES)
    # Correction 6: check len(data) after read
    if len(data) >= MAX_BYTES:
        raise ValueError("source file exceeds 2 MiB limit")
    return data.decode("utf-8-sig")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="update_rules.py",
        description="Parse 1stream xray rules and generate per-region YAML.",
    )
    parser.add_argument("--source-file", type=str, default=None,
                        help="Local source file (default: fetch from SOURCE_URL)")
    parser.add_argument("--output-dir", type=str,
                        default=str(Path(__file__).resolve().parents[1] / "rules"),
                        help="Output directory for YAML files")
    parser.add_argument("--dns-server", type=str, default=DEFAULT_DNS,
                        help="DNS server URL for generated YAML")
    parser.add_argument("--check", action="store_true",
                        help="Check mode: report diffs without writing")
    args = parser.parse_args(argv)

    try:
        if args.source_file:
            text = _read_local(args.source_file)
        else:
            text = _fetch(SOURCE_URL)

        outputs = generate(text, dns_server=args.dns_server)
        output_dir = Path(args.output_dir)
        changed = update_files(outputs, output_dir, check=args.check)

    except (ValueError, OSError, urllib.error.URLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Print per-region dedup counts
    for fname in sorted(outputs.keys()):
        content = outputs[fname]
        rule_count = sum(1 for ln in content.splitlines() if ln.strip().startswith("- "))
        code = fname.removesuffix(".yml")
        print(f"{code}: {rule_count} rules")

    if changed:
        if args.check:
            print(f"check: {len(changed)} file(s) differ: {', '.join(changed)}")
            return 1
        print(f"updated: {', '.join(changed)}")
    else:
        print("no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
