"""Tests for the description of an uploaded file made from its yt-dlp metadata.

The user downloads the video with yt-dlp --write-info-json, uploads it, and
adds the .info.json file: the description must then be the same as for the URL
of the video, and must stay well-formed whatever the file contains.
"""

import json
import logging

import pytest

from video2commons.frontend import api, urlextract

YOUTUBE_URL = "https://www.youtube.com/watch?v=abcdefghijk"
COMMONS_FILE = "https://commons.wikimedia.org/entity/M123"

# The fields that the description uses, as in an .info.json file of YouTube.
YOUTUBE_INFO = {
    "id": "abcdefghijk",
    "title": "Example video",
    "description": "An example.",
    "uploader": "Example channel",
    "uploader_url": "https://www.youtube.com/@example",
    "upload_date": "20240102",
    "license": "Creative Commons Attribution license (reuse allowed)",
    "webpage_url": YOUTUBE_URL,
    "extractor": "youtube",
    "extractor_key": "Youtube",
}
YOUTUBE_DESC = """=={{int:filedesc}}==
{{Information
|description=An example.
|date=2024-01-02
|source={{From YouTube|1=abcdefghijk|2=Example video}}
|author=[https://www.youtube.com/@example Example channel]
|permission=
|other_versions=
|other_fields=
}}

=={{int:license-header}}==
{{YouTube CC-BY|Example channel}}
{{LicenseReview}}

[[Category:Uploaded with video2commons]]"""
CLEANED_YOUTUBE_INFO = {"formats": [], **YOUTUBE_INFO}

# Values of the wrong type, which yt-dlp never writes for these fields.
WRONG_TYPES = [None, 1, 1.5, True, [], {}, ["text"], {"text": "text"}]


def youtube_info(**fields):
    """Get YOUTUBE_INFO with some fields changed, or removed if None."""
    info = {**YOUTUBE_INFO, **fields}
    return {key: value for key, value in info.items() if value is not None}


def cleaned_info(**fields):
    """Get CLEANED_YOUTUBE_INFO with some fields changed."""
    return {**CLEANED_YOUTUBE_INFO, **fields}


class TestCleanInfo:
    def test_keeps_valid_fields(self):
        assert urlextract.clean_info(YOUTUBE_INFO) == CLEANED_YOUTUBE_INFO

    def test_does_not_change_the_metadata(self):
        info = youtube_info(formats=[{"url": "https://example.com/video.webm"}])
        copy = json.loads(json.dumps(info))

        urlextract.clean_info(info)

        assert info == copy

    def test_leaves_out_other_fields(self):
        info = youtube_info(
            formats=[{"url": "https://example.com/video.webm"}],
            direct=True,
            url="https://example.com/video.webm",
            width=3840,
            thumbnails=[{"url": "https://example.com/thumbnail.jpg"}],
        )

        assert urlextract.clean_info(info) == CLEANED_YOUTUBE_INFO

    @pytest.mark.parametrize("info_type", [None, "video"])
    def test_accepts_a_single_video(self, info_type):
        info = {**YOUTUBE_INFO, "_type": info_type}

        assert urlextract.clean_info(info) == CLEANED_YOUTUBE_INFO

    @pytest.mark.parametrize(
        "field", [field for field in urlextract.INFO_FIELDS if field != "extractor"]
    )
    def test_missing_field_is_empty(self, field):
        info = youtube_info(**{field: None})

        assert urlextract.clean_info(info) == cleaned_info(**{field: ""})

    @pytest.mark.parametrize(
        "field", [field for field in urlextract.INFO_FIELDS if field != "extractor"]
    )
    @pytest.mark.parametrize("value", WRONG_TYPES)
    def test_field_of_the_wrong_type_is_empty(self, field, value):
        info = {**YOUTUBE_INFO, field: value}

        assert urlextract.clean_info(info) == cleaned_info(**{field: ""})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("id", "a" * 20000),
            ("uploader_url", "https://www.youtube.com/@" + "a" * 19975),
            *[
                (field, "a" * 20000)
                for field in ("title", "description", "uploader", "license")
            ],
        ],
    )
    def test_field_of_the_maximum_length_is_kept(self, field, value):
        info = {**YOUTUBE_INFO, field: value}

        assert urlextract.clean_info(info) == cleaned_info(**{field: value})

    @pytest.mark.parametrize(
        "field", [field for field in urlextract.INFO_FIELDS if field != "extractor"]
    )
    def test_field_longer_than_the_maximum_is_empty(self, field):
        value = {
            "id": "a" * 20001,
            "uploader_url": "https://www.youtube.com/@" + "a" * 19976,
            "upload_date": "2" * 20001,
        }.get(field, "a" * 20001)
        info = {**YOUTUBE_INFO, field: value}

        assert urlextract.clean_info(info) == cleaned_info(**{field: ""})

    @pytest.mark.parametrize(
        "video_id", ["abcdefghijk", "ABC-def_123", "1234567890", "a.b-c_d", "a"]
    )
    def test_keeps_a_valid_id(self, video_id):
        info = youtube_info(id=video_id)

        assert urlextract.clean_info(info) == cleaned_info(id=video_id)

    @pytest.mark.parametrize(
        "video_id",
        [
            "",
            "abc defghijk",
            "abcdefghijk|2=Other title",
            "abcdefghijk}}",
            "{{abcdefghijk",
            "[[abcdefghijk]]",
            'abcdefghijk" } #',
            "abcdefghijk\n",
            "ab/cdefghijk",
            "abcdéfghijk",
        ],
    )
    def test_invalid_id_is_empty(self, video_id):
        info = youtube_info(id=video_id)

        assert urlextract.clean_info(info) == cleaned_info(id="")

    @pytest.mark.parametrize(
        "date",
        [
            "",
            "2024-01-02",
            "2024010",
            "202401023",
            "2024010a",
            "20240102\n",
            " 20240102",
            "20240102}}{{Delete",
            "２０２４０１０２",
        ],
    )
    def test_invalid_upload_date_is_empty(self, date):
        info = youtube_info(upload_date=date)

        assert urlextract.clean_info(info) == cleaned_info(upload_date="")

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/@example",
            "http://www.youtube.com/channel/UC123",
            "https://example.com/a?b=c&d=e#f",
            "https://example.com/%5B%5D",
        ],
    )
    def test_keeps_a_valid_uploader_url(self, url):
        info = youtube_info(uploader_url=url)

        assert urlextract.clean_info(info) == cleaned_info(uploader_url=url)

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "www.youtube.com/@example",
            "//www.youtube.com/@example",
            "ftp://www.youtube.com/@example",
            "javascript:alert(1)",
            "HTTPS://www.youtube.com/@example",
            "https://",
            "https://www.youtube.com/@example Other text",
            "https://www.youtube.com/@example]] [[Category:Other",
            "https://www.youtube.com/@example[1]",
            "https://www.youtube.com/@example|other",
            "https://www.youtube.com/@example{{Delete}}",
            "https://www.youtube.com/<script>",
            'https://www.youtube.com/"onclick',
            "https://www.youtube.com/@example\n",
            "https://www.youtube.com/@ex\tample",
            " https://www.youtube.com/@example",
        ],
    )
    def test_invalid_uploader_url_is_empty(self, url):
        info = youtube_info(uploader_url=url)

        assert urlextract.clean_info(info) == cleaned_info(uploader_url="")

    @pytest.mark.parametrize("field", ["title", "description", "uploader", "license"])
    @pytest.mark.parametrize(
        "value", ["", "]] {{Delete}} [[Category:Other]] | ~~~~", "Vidéo 日本語 🎥\n"]
    )
    def test_keeps_any_text(self, field, value):
        # The description escapes this text, or only compares it.
        info = youtube_info(**{field: value})

        assert urlextract.clean_info(info) == cleaned_info(**{field: value})

    @pytest.mark.parametrize("extractor", ["youtube", "vimeo:album", "Any name | }}"])
    def test_keeps_any_extractor_name(self, extractor):
        # The description only compares it with the names of the extractors.
        info = youtube_info(extractor=extractor)

        assert urlextract.clean_info(info) == cleaned_info(extractor=extractor)

    @pytest.mark.parametrize("extractor", [None, "", *WRONG_TYPES, "a" * 20001])
    def test_invalid_extractor_name_is_the_extractor_key(self, extractor):
        info = {**YOUTUBE_INFO, "extractor": extractor}
        if extractor is None:
            del info["extractor"]

        assert urlextract.clean_info(info) == cleaned_info(extractor="Youtube")

    @pytest.mark.parametrize("info", [None, [], [YOUTUBE_INFO], "text", 1, 1.5, True])
    def test_rejects_other_json_values(self, info):
        with pytest.raises(
            AssertionError, match="^The metadata file must contain a JSON object$"
        ):
            urlextract.clean_info(info)

    @pytest.mark.parametrize(
        "info_type", ["playlist", "multi_video", "url", "url_transparent", "", 1]
    )
    def test_rejects_other_types(self, info_type):
        info = youtube_info(_type=info_type)

        with pytest.raises(
            AssertionError,
            match="^The metadata file must describe a single video, not a playlist$",
        ):
            urlextract.clean_info(info)

    @pytest.mark.parametrize(
        "extractor_key",
        [
            None,
            "",
            *WRONG_TYPES[1:],
            "You tube",
            "Youtube}}",
            "Youtube\n",
            "Yöutube",
            "Youtube:Tab",
            "a" * 20001,
        ],
    )
    def test_rejects_an_invalid_extractor_key(self, extractor_key):
        info = youtube_info(extractor_key=extractor_key)

        with pytest.raises(
            AssertionError,
            match=(
                "^The metadata file has no valid extractor_key: "
                r"is it an \.info\.json file written by yt-dlp\?$"
            ),
        ):
            urlextract.clean_info(info)

    def test_keeps_an_extractor_key_of_the_maximum_length(self):
        info = youtube_info(extractor_key="A" * 20000)

        assert urlextract.clean_info(info)["extractor_key"] == "A" * 20000

    @pytest.mark.parametrize(
        "url",
        [
            None,
            "",
            *WRONG_TYPES[1:],
            "www.youtube.com/watch?v=abcdefghijk",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "https://www.youtube.com/watch?v=abcdefghijk Other title",
            "https://www.youtube.com/watch?v=abcdefghijk]] [[Category:Other",
            "https://www.youtube.com/watch?v=abcdefghijk|other",
            "https://www.youtube.com/watch?v=abcdefghijk}}",
            "https://www.youtube.com/watch?v=abcdefghijk\n",
            "https://www.youtube.com/" + "a" * 19977,
        ],
    )
    def test_rejects_an_invalid_webpage_url(self, url):
        info = youtube_info(webpage_url=url)

        with pytest.raises(
            AssertionError, match="^The metadata file has no valid webpage_url$"
        ):
            urlextract.clean_info(info)

    def test_keeps_a_webpage_url_of_the_maximum_length(self):
        url = "https://www.youtube.com/" + "a" * 19976
        info = youtube_info(webpage_url=url)

        assert urlextract.clean_info(info)["webpage_url"] == url


class TestMakeInfoDesc:
    def make_desc(self, filename="video.webm", **fields):
        info = urlextract.clean_info(youtube_info(**fields))
        return urlextract.make_info_desc(filename, info)

    def test_youtube_video(self):
        assert self.make_desc() == {
            "extractor": "(uploads)",
            "filedesc": YOUTUBE_DESC,
            "filename": "Example video",
        }

    def test_is_the_description_of_the_url(self):
        # The same description as extracturl, which gets the full metadata
        # from yt-dlp.
        info = youtube_info(formats=[{"url": "https://example.com/video.webm"}])
        extracted = urlextract._extract_info(info)

        desc = self.make_desc()

        assert desc["filedesc"] == extracted["filedesc"]
        assert desc["filename"] == extracted["filename"]

    def test_youtube_cc_by_4(self):
        desc = self.make_desc(upload_date="20250802")

        assert "|date=2025-08-02\n" in desc["filedesc"]
        assert "\n{{YouTube CC-BY 4.0|Example channel}}\n" in desc["filedesc"]

    def test_youtube_video_without_a_free_license(self):
        desc = self.make_desc(license="Standard YouTube License")

        assert f"\n{urlextract.DEFAULT_LICENSE}\n" in desc["filedesc"]

    def test_youtube_video_without_a_license(self):
        desc = self.make_desc(license=None)

        assert f"\n{urlextract.DEFAULT_LICENSE}\n" in desc["filedesc"]

    def test_vimeo_video(self):
        desc = self.make_desc(
            id="123456",
            webpage_url="https://vimeo.com/123456",
            uploader_url="https://vimeo.com/example",
            license="by-sa",
            extractor="vimeo",
            extractor_key="Vimeo",
        )

        assert "|source={{From Vimeo|1=123456|2=Example video}}\n" in desc["filedesc"]
        assert (
            "|author=[https://vimeo.com/example Example channel]\n"
            in (desc["filedesc"])
        )
        assert "\n{{cc-by-sa-3.0|Example channel}}\n" in desc["filedesc"]

    def test_video_of_another_site(self):
        desc = self.make_desc(
            id="42",
            webpage_url="https://example.com/videos/42",
            license="Attribution",
            extractor="flickr",
            extractor_key="Flickr",
        )

        assert (
            "|source=[https://example.com/videos/42 Example video - Flickr]\n"
            in desc["filedesc"]
        )
        # Flickr licenses were 2.0 before 2025-06-18.
        assert "\n{{cc-by-2.0|Example channel}}\n" in desc["filedesc"]

    def test_video_of_a_sub_extractor(self):
        # The source names the site of the extractor, not the sub-extractor.
        desc = self.make_desc(
            id="42",
            webpage_url="https://vimeo.com/album/42",
            extractor="vimeo:album",
            extractor_key="VimeoAlbum",
        )

        assert (
            "|source=[https://vimeo.com/album/42 Example video - Vimeo]\n"
            in desc["filedesc"]
        )

    def test_generic_video(self):
        desc = self.make_desc(
            id="video",
            webpage_url="https://example.com/video.webm",
            extractor="generic",
            extractor_key="Generic",
        )

        assert "|source=https://example.com/video.webm\n" in desc["filedesc"]

    def test_escapes_the_text(self):
        desc = self.make_desc(
            title="Title]] {{Delete}} | [[Category:Other",
            description="Description]] {{Delete}} | [[Category:Other",
            uploader="Uploader]] {{Delete}} | [[Category:Other",
        )

        for text in ("Title", "Description", "Uploader"):
            assert (
                f"{text}{{{{))!}}}} {{{{((}}}}Delete{{{{))}}}} &#124; "
                "{{!((}}Category:Other"
            ) in desc["filedesc"]
        assert "[[Category:Other" not in desc["filedesc"]
        assert "{{Delete}}" not in desc["filedesc"]

    def test_invalid_id(self):
        desc = self.make_desc(id="abcdefghijk|2=Other title")

        assert f"|source=[{YOUTUBE_URL} Example video - Youtube]\n" in desc["filedesc"]
        assert "Other title" not in desc["filedesc"]

    def test_invalid_upload_date(self):
        desc = self.make_desc(upload_date="20240102}}{{Delete")

        assert "|date=\n" in desc["filedesc"]
        assert "Delete" not in desc["filedesc"]

    def test_invalid_uploader_url(self):
        desc = self.make_desc(uploader_url="https://example.com/ [[Category:Other]]")

        assert "|author=Example channel\n" in desc["filedesc"]
        assert "Category:Other" not in desc["filedesc"]

    def test_only_the_webpage_url(self):
        info = urlextract.clean_info(
            {"webpage_url": "https://example.com/video", "extractor_key": "Generic"}
        )

        desc = urlextract.make_info_desc("My video.webm", info)

        assert desc == {
            "extractor": "(uploads)",
            "filedesc": urlextract.FILEDESC_TEMPLATE.strip()
            % {
                "desc": "",
                "date": "",
                "source": "https://example.com/video",
                "uploader": "",
                "license": urlextract.DEFAULT_LICENSE,
            },
            "filename": "My video",
        }

    def test_filename_is_sanitized(self):
        desc = self.make_desc(title="A: title / with # forbidden [characters]")

        assert desc["filename"] == urlextract.sanitize(
            "A: title / with # forbidden [characters]"
        )

    @pytest.mark.parametrize("title", [None, "", "   "])
    def test_filename_without_a_title(self, title):
        desc = self.make_desc(filename="My video.webm", title=title)

        assert desc["filename"] == "My video"


@pytest.fixture
def youtube_ids(monkeypatch):
    """The YouTube IDs looked up on Commons, which has none of them."""
    ids = []

    def find(youtube_id):
        ids.append(youtube_id)

    monkeypatch.setattr(api, "do_validate_youtube_id", find)
    return ids


class TestMakeDescEndpoint:
    @pytest.mark.parametrize("info", [{}, {"info": ""}])
    def test_without_metadata(self, api_post, youtube_ids, info):
        data = api_post("makedesc", filename="My video.webm", **info)

        assert data == urlextract.make_dummy_desc("My video.webm")
        assert youtube_ids == []

    def test_with_metadata(self, api_post, youtube_ids):
        data = api_post(
            "makedesc", filename="video.webm", info=json.dumps(YOUTUBE_INFO)
        )

        assert data == {
            "extractor": "(uploads)",
            "filedesc": YOUTUBE_DESC,
            "filename": "Example video",
        }
        assert youtube_ids == ["abcdefghijk"]

    def test_cleans_the_metadata(self, api_post, youtube_ids):
        info = youtube_info(upload_date="2024-01-02}}", formats=[{"url": "x"}])

        data = api_post("makedesc", filename="video.webm", info=json.dumps(info))

        assert "|date=\n" in data["filedesc"]
        assert "}}" not in data["filedesc"].split("|date=")[1].split("\n")[0]

    @pytest.mark.parametrize("info", ["{", "not json", "{'id': 'a'}", "﻿{}"])
    def test_invalid_json(self, api_post, youtube_ids, info):
        data = api_post("makedesc", filename="video.webm", info=info)

        assert data["step"] == "error"
        assert data["error"] == "The metadata file is not valid JSON"
        assert youtube_ids == []

    @pytest.mark.parametrize(
        ("info", "error"),
        [
            ([], "The metadata file must contain a JSON object"),
            (
                {**YOUTUBE_INFO, "_type": "playlist"},
                "The metadata file must describe a single video, not a playlist",
            ),
            (
                youtube_info(extractor_key=None),
                (
                    "The metadata file has no valid extractor_key: "
                    "is it an .info.json file written by yt-dlp?"
                ),
            ),
            (
                youtube_info(webpage_url=None),
                "The metadata file has no valid webpage_url",
            ),
        ],
    )
    def test_invalid_metadata(self, api_post, youtube_ids, info, error):
        data = api_post("makedesc", filename="video.webm", info=json.dumps(info))

        assert data["step"] == "error"
        assert data["error"] == error
        assert youtube_ids == []

    def test_youtube_video_already_on_commons(self, api_post, monkeypatch):
        monkeypatch.setattr(api, "do_validate_youtube_id", lambda id: COMMONS_FILE)

        data = api_post(
            "makedesc", filename="video.webm", info=json.dumps(YOUTUBE_INFO)
        )

        assert data["step"] == "error"
        assert data["error"] == f"This video has already been uploaded: {COMMONS_FILE}"

    def test_youtube_video_with_an_invalid_id(self, api_post, youtube_ids):
        # The ID would otherwise be inserted in the query of Commons.
        info = youtube_info(id='abcdefghijk" } #')

        data = api_post("makedesc", filename="video.webm", info=json.dumps(info))

        assert data["filename"] == "Example video"
        assert youtube_ids == []

    def test_video_of_another_site(self, api_post, youtube_ids):
        info = youtube_info(
            webpage_url="https://vimeo.com/123456", extractor_key="Vimeo"
        )

        data = api_post("makedesc", filename="video.webm", info=json.dumps(info))

        assert data["filename"] == "Example video"
        assert youtube_ids == []

    def test_lookup_failure_is_ignored(self, api_post, monkeypatch, caplog):
        def fail(youtube_id):
            raise RuntimeError("SPARQL is down")

        monkeypatch.setattr(api, "do_validate_youtube_id", fail)

        with caplog.at_level(logging.ERROR):
            data = api_post(
                "makedesc",
                filename="video.webm",
                info=json.dumps(YOUTUBE_INFO),
            )

        assert data["filedesc"] == YOUTUBE_DESC
        assert 'Error validating YouTube ID "abcdefghijk"' in caplog.text

    def test_requires_the_csrf_token(self, client, youtube_ids):
        response = client.post(
            "/api/makedesc",
            data={"filename": "video.webm", "info": json.dumps(YOUTUBE_INFO)},
        )

        assert response.get_json()["error"] == (
            "Invalid CSRF token. Try reloading this page."
        )
        assert youtube_ids == []


class TestValidateUrlEndpoint:
    def test_youtube_video_not_on_commons(self, api_post, youtube_ids):
        data = api_post("validateurl", url=YOUTUBE_URL)

        assert data == {"entity_url": None}
        assert youtube_ids == ["abcdefghijk"]

    def test_youtube_video_already_on_commons(self, api_post, monkeypatch):
        ids = []

        def find(youtube_id):
            ids.append(youtube_id)
            return COMMONS_FILE

        monkeypatch.setattr(api, "do_validate_youtube_id", find)

        data = api_post("validateurl", url="https://youtu.be/abcdefghijk")

        assert data == {"entity_url": COMMONS_FILE}
        assert ids == ["abcdefghijk"]

    def test_lookup_failure_is_ignored(self, api_post, monkeypatch, caplog):
        def fail(youtube_id):
            raise RuntimeError("SPARQL is down")

        monkeypatch.setattr(api, "do_validate_youtube_id", fail)

        with caplog.at_level(logging.ERROR):
            data = api_post("validateurl", url=YOUTUBE_URL)

        assert data == {"entity_url": None}
        assert 'Error validating YouTube ID "abcdefghijk"' in caplog.text

    def test_video_of_another_site(self, api_post, youtube_ids):
        data = api_post("validateurl", url="https://vimeo.com/123456")

        assert data == {"entity_url": None}
        assert youtube_ids == []
