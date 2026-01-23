# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>

"""Helper functions for working with MediaWiki categories."""

import json
import subprocess

from typing import Iterable, Set

from ..encode.globals import ffprobe_location


def get_subtitle_categories(langcodes: Iterable[str]) -> Set[str]:
    """Map a set of language codes to MediaWiki categories."""
    categories = set()

    for langcode in langcodes:
        category = SUBTITLE_CATEGORY_MAPPING.get(langcode)
        if category:
            categories.add(f"[[Category:{category}]]")

    return categories


def get_inferable_categories(source: str) -> Set[str]:
    """Get categories that can be inferred from the source metadata."""
    categories = set()

    result = subprocess.run([
        ffprobe_location,
        '-loglevel', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=index,codec_type',
        '-of', 'json',
        source
    ], capture_output=True, text=True)

    has_audio = False

    if result.returncode == 0:
        for stream in json.loads(result.stdout).get('streams', []):
            if stream.get('codec_type') == 'audio':
                has_audio = True
                break

    if not has_audio:
        categories.add('[[Category:Videos without audio]]')

    return categories


def append_categories(filedesc: str, categories: Iterable[str]) -> str:
    """Append MediaWiki categories to a file description."""

    for category in categories:
        if category in filedesc:
            continue  # Don't duplicate if the user already added them.

        filedesc += f"\n{category}"

    return filedesc


SUBTITLE_CATEGORY_MAPPING = {
    "ab": "Videos with Abkhaz subtitles",
    "aa": "Videos with Afar subtitles",
    "af": "Videos with Afrikaans subtitles",
    "am": "Videos with Amharic subtitles",
    "grc": "Videos with Ancient Greek subtitles",
    "ar": "Videos with Arabic subtitles",
    "hy": "Videos with Armenian subtitles",
    "as": "Videos with Assamese subtitles",
    "av": "Videos with Avar subtitles",
    "az": "Videos with Azerbaijani subtitles",
    "bm": "Videos with Bambara subtitles",
    "ba": "Videos with Bashkir subtitles",
    "eu": "Videos with Basque subtitles",
    "be": "Videos with Belarusian subtitles",
    "bn": "Videos with Bengali subtitles",
    "bs": "Videos with Bosnian subtitles",
    "pt-BR": "Videos with Brazilian Portuguese subtitles",
    "br": "Videos with Breton subtitles",
    "en-GB": "Videos with British English subtitles",
    "bg": "Videos with Bulgarian subtitles",
    "yue": "Videos with Cantonese subtitles",
    "ca": "Videos with Catalan subtitles",
    "zh": "Videos with Chinese subtitles",
    "kw": "Videos with Cornish subtitles",
    "co": "Videos with Corsican subtitles",
    "hr": "Videos with Croatian subtitles",
    "cs": "Videos with Czech subtitles",
    "da": "Videos with Danish subtitles",
    "nl": "Videos with Dutch subtitles",
    "en": "Videos with English subtitles",
    "eo": "Videos with Esperanto subtitles",
    "et": "Videos with Estonian subtitles",
    "fo": "Videos with Faroese subtitles",
    "fj": "Videos with Fijian subtitles",
    "fi": "Videos with Finnish subtitles",
    "fr": "Videos with French subtitles",
    "ff": "Videos with Fulfulde subtitles",
    "gl": "Videos with Galician subtitles",
    "ka": "Videos with Georgian subtitles",
    "de": "Videos with German subtitles",
    "el": "Videos with Greek subtitles",
    "gn": "Videos with Guaraní subtitles",
    "gu": "Videos with Gujarati subtitles",
    "ht": "Videos with Haitian Creole French subtitles",
    "khk": "Videos with Halh Mongolian subtitles",
    "ha": "Videos with Hausa subtitles",
    "haw": "Videos with Hawaiian subtitles",
    "he": "Videos with Hebrew subtitles",
    "hi": "Videos with Hindi subtitles",
    "hu": "Videos with Hungarian subtitles",
    "is": "Videos with Icelandic subtitles",
    "ig": "Videos with Igbo subtitles",
    "id": "Videos with Indonesian subtitles",
    "iu": "Videos with Inuktitut subtitles",
    "ga": "Videos with Irish subtitles",
    "it": "Videos with Italian subtitles",
    "ja": "Videos with Japanese subtitles",
    "jv": "Videos with Javanese subtitles",
    "kn": "Videos with Kannada subtitles",
    "kk": "Videos with Kazakh subtitles",
    "rw": "Videos with Kinyarwanda subtitles",
    "ko": "Videos with Korean subtitles",
    "ky": "Videos with Kyrgyz subtitles",
    "lo": "Videos with Laotian subtitles",
    "la": "Videos with Latin subtitles",
    "lv": "Videos with Latvian subtitles",
    "lt": "Videos with Lithuanian subtitles",
    "jbo": "Videos with Lojban subtitles",
    "nds": "Videos with Low German subtitles",
    "lb": "Videos with Luxembourgish subtitles",
    "mk": "Videos with Macedonian subtitles",
    "mai": "Videos with Maithili subtitles",
    "ms": "Videos with Malay subtitles",
    "ml": "Videos with Malayalam subtitles",
    "mt": "Videos with Maltese subtitles",
    "mi": "Videos with Maori subtitles",
    "mr": "Videos with Marathi subtitles",
    "mwl": "Videos with Mirandese subtitles",
    "lus": "Videos with Mizo/Lushai subtitles",
    "ne": "Videos with Nepali subtitles",
    "nb": "Videos with Norwegian Bokmål subtitles",
    "no": "Videos with Norwegian subtitles",
    "oc": "Videos with Occitan subtitles",
    "om": "Videos with Oromo subtitles",
    "pap": "Videos with Papiamentu subtitles",
    "ps": "Videos with Pashto subtitles",
    "fa": "Videos with Persian subtitles",
    "pl": "Videos with Polish subtitles",
    "pt": "Videos with Portuguese subtitles",
    "pa": "Videos with Punjabi subtitles",
    "qu": "Videos with Quechua subtitles",
    "ro": "Videos with Romanian subtitles",
    "ru": "Videos with Russian subtitles",
    "sm": "Videos with Samoan subtitles",
    "sa": "Videos with Sanskrit subtitles",
    "sr-Cyrl": "Videos with Serbian Cyrillic subtitles",
    "sr": "Videos with Serbian subtitles",
    "tn": "Videos with Setswana subtitles",
    "sn": "Videos with Shona subtitles",
    "scn": "Videos with Sicilian subtitles",
    "sd": "Videos with Sindhi subtitles",
    "si": "Videos with Sinhalese subtitles",
    "sk": "Videos with Slovak subtitles",
    "sl": "Videos with Slovenian subtitles",
    "so": "Videos with Somali subtitles",
    "st": "Videos with Southern Sotho subtitles",
    "es": "Videos with Spanish subtitles",
    "su": "Videos with Sundanese subtitles",
    "ss": "Videos with Swati subtitles",
    "syl": "Videos with Sylheti subtitles",
    "tl": "Videos with Tagalog subtitles",
    "tzm": "Videos with Tamazight subtitles",
    "ta": "Videos with Tamil subtitles",
    "te": "Videos with Telugu subtitles",
    "th": "Videos with Thai subtitles",
    "ti": "Videos with Tigrinya subtitles",
    "tok": "Videos with Toki Pona subtitles",
    "tpi": "Videos with Tok Pisin subtitles",
    "to": "Videos with Tonga subtitles",
    "ts": "Videos with Tsonga subtitles",
    "tr": "Videos with Turkish subtitles",
    "tk": "Videos with Turkmen subtitles",
    "tyv": "Videos with Tuvan subtitles",
    "uk": "Videos with Ukrainian subtitles",
    "uz": "Videos with Uzbek subtitles",
    "ve": "Videos with Venda subtitles",
    "vi": "Videos with Vietnamese subtitles",
    "cy": "Videos with Welsh subtitles",
    "fy": "Videos with West Frisian subtitles",
    "wo": "Videos with Wolof subtitles",
    "xh": "Videos with Xhosa subtitles",
    "yi": "Videos with Yiddish subtitles",
    "yo": "Videos with Yoruba subtitles",
    "zu": "Videos with Zulu subtitles",
    "ee": "Videos with Éwé subtitles",
}
