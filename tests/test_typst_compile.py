import subprocess
import shutil
from pathlib import Path
import pytest
import yaml
from jobhunt.profile import load_candidate_profile, export_profile_for_typst

TYPST_AVAILABLE = shutil.which("typst") is not None


@pytest.mark.skipif(not TYPST_AVAILABLE, reason="typst CLI is not installed")
def test_typst_cv_compile_with_profile():
    root = Path(__file__).resolve().parents[1]
    cv_typ = root / "Base" / "cv.typ"
    profile = load_candidate_profile(root / "config" / "profile.example.yaml")
    profile_data = export_profile_for_typst(profile)

    test_dir = root / ".tmp_test_typst"
    test_dir.mkdir(exist_ok=True)
    try:
        profile_file = test_dir / "profile.yaml"
        profile_file.write_text(yaml.safe_dump(profile_data), encoding="utf-8")

        cv_data = {
            "title": "Marketing Manager",
            "tagline": "Specialist in B2B growth and multi-channel campaigns",
            "profile": "Experienced marketer with a track record of driving revenue and owning campaigns end to end.",
            "max_pages": 1,
            "variant": "grotesk_one_page",
            "experience": [
                {
                    "company": "Tech Corp",
                    "role": "Marketing Lead",
                    "period": "2023 - Present",
                    "location": "Amsterdam",
                    "bullets": ["Led GTM for flagship platform driving 35% growth."],
                }
            ],
        }
        cv_data_file = test_dir / "cv-data.yaml"
        cv_data_file.write_text(yaml.safe_dump(cv_data), encoding="utf-8")

        out_pdf = test_dir / "cv.pdf"
        rel_cv_data = f"/{cv_data_file.relative_to(root).as_posix()}"
        rel_profile = f"/{profile_file.relative_to(root).as_posix()}"

        cmd = [
            "typst",
            "compile",
            "--root",
            str(root),
            str(cv_typ),
            str(out_pdf),
            "--input",
            f"data={rel_cv_data}",
            "--input",
            f"profile={rel_profile}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Typst compile failed: {res.stderr}"
        assert out_pdf.exists()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@pytest.mark.skipif(not TYPST_AVAILABLE, reason="typst CLI is not installed")
@pytest.mark.parametrize("variant", ["grotesk_one_page", "compact_one_page", "classic_two_page", "enriched_two_page"])
def test_typst_cv_all_variants_compile(variant: str):
    root = Path(__file__).resolve().parents[1]
    cv_typ = root / "Base" / "cv.typ"
    profile = load_candidate_profile(root / "config" / "profile.example.yaml")
    profile_data = export_profile_for_typst(profile)

    test_dir = root / ".tmp_test_typst"
    test_dir.mkdir(exist_ok=True)
    try:
        profile_file = test_dir / f"profile_{variant}.yaml"
        profile_file.write_text(yaml.safe_dump(profile_data), encoding="utf-8")

        max_pages = 1 if "one_page" in variant else 2
        cv_data = {
            "title": "Product Marketing Lead",
            "tagline": "Specialist in B2B SaaS growth and lifecycle marketing.",
            "profile": "Experienced marketer with a track record of driving revenue and owning campaigns end to end.",
            "max_pages": max_pages,
            "variant": variant,
            "selected_highlights": ["Generated 40% inbound pipeline growth."] if variant == "enriched_two_page" else [],
            "experience": [
                {
                    "company": "Tech Corp",
                    "role": "Marketing Lead",
                    "period": "2023 - Present",
                    "location": "Amsterdam, NL",
                    "bullets": [
                        "Led GTM for flagship platform driving 35% growth.",
                        "Built lifecycle automated nurture flows in CRM.",
                    ],
                }
            ],
            "additional": [
                {
                    "company": "StartupX",
                    "role": "Growth Marketer",
                    "period": "2021 - 2023",
                    "location": "Rotterdam, NL",
                    "bullets": ["Optimized conversion funnel."],
                }
            ] if "two_page" in variant else [],
        }
        cv_data_file = test_dir / f"cv_data_{variant}.yaml"
        cv_data_file.write_text(yaml.safe_dump(cv_data), encoding="utf-8")

        out_pdf = test_dir / f"cv_{variant}.pdf"
        rel_cv_data = f"/{cv_data_file.relative_to(root).as_posix()}"
        rel_profile = f"/{profile_file.relative_to(root).as_posix()}"

        cmd = [
            "typst",
            "compile",
            "--root",
            str(root),
            str(cv_typ),
            str(out_pdf),
            "--input",
            f"data={rel_cv_data}",
            "--input",
            f"profile={rel_profile}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Typst CV compile failed for variant '{variant}': {res.stderr}"
        assert out_pdf.exists()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@pytest.mark.skipif(not TYPST_AVAILABLE, reason="typst CLI is not installed")
def test_typst_letter_compile_with_profile():
    root = Path(__file__).resolve().parents[1]
    letter_typ = root / "Base" / "letter.typ"
    profile = load_candidate_profile(root / "config" / "profile.example.yaml")
    profile_data = export_profile_for_typst(profile)

    test_dir = root / ".tmp_test_typst"
    test_dir.mkdir(exist_ok=True)
    try:
        profile_file = test_dir / "profile_letter.yaml"
        profile_file.write_text(yaml.safe_dump(profile_data), encoding="utf-8")

        letter_data = {
            "max_pages": 1,
            "subtitle": "Product Marketing Lead — TechCorp",
            "paragraphs": [
                "I am applying for the Product Marketing Lead position. Building scalable growth is my core strength.",
                "At my previous company I led full-funnel marketing campaigns and scaled inbound pipeline by 35%.",
                "I look forward to discussing how my experience can support your growth objectives.",
            ],
        }
        letter_data_file = test_dir / "letter_data.yaml"
        letter_data_file.write_text(yaml.safe_dump(letter_data), encoding="utf-8")

        out_pdf = test_dir / "letter.pdf"
        rel_letter_data = f"/{letter_data_file.relative_to(root).as_posix()}"
        rel_profile = f"/{profile_file.relative_to(root).as_posix()}"

        cmd = [
            "typst",
            "compile",
            "--root",
            str(root),
            str(letter_typ),
            str(out_pdf),
            "--input",
            f"data={rel_letter_data}",
            "--input",
            f"profile={rel_profile}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Typst letter compile failed: {res.stderr}"
        assert out_pdf.exists()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@pytest.mark.skipif(not TYPST_AVAILABLE, reason="typst CLI is not installed")
def test_reference_cv_and_letter_compile():
    root = Path(__file__).resolve().parents[1]
    cv_typ = root / "Base" / "cv.typ"
    letter_typ = root / "Base" / "letter.typ"

    test_dir = root / ".tmp_test_typst"
    test_dir.mkdir(exist_ok=True)
    try:
        # Test reference CV
        out_cv_pdf = test_dir / "reference_cv.pdf"
        cmd_cv = [
            "typst",
            "compile",
            "--root",
            str(root),
            str(cv_typ),
            str(out_cv_pdf),
            "--input",
            "data=/Base/reference/cv-data.yaml",
        ]
        res_cv = subprocess.run(cmd_cv, capture_output=True, text=True)
        assert res_cv.returncode == 0, f"Reference CV compile failed: {res_cv.stderr}"
        assert out_cv_pdf.exists()

        # Test reference letter
        out_letter_pdf = test_dir / "reference_letter.pdf"
        cmd_letter = [
            "typst",
            "compile",
            "--root",
            str(root),
            str(letter_typ),
            str(out_letter_pdf),
            "--input",
            "data=/Base/reference/letter-data.yaml",
        ]
        res_letter = subprocess.run(cmd_letter, capture_output=True, text=True)
        assert res_letter.returncode == 0, f"Reference letter compile failed: {res_letter.stderr}"
        assert out_letter_pdf.exists()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
