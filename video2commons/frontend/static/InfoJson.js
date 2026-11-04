/**
 * The fields of a yt-dlp .info.json file that the description of an uploaded
 * file uses. The file also has the formats, thumbnails and subtitles of the
 * video, often several megabytes that the server doesn't need.
 */
const INFO_FIELDS = [
	"_type",
	"id",
	"title",
	"description",
	"uploader",
	"uploader_url",
	"upload_date",
	"license",
	"webpage_url",
	"extractor",
	"extractor_key",
];

// The .info.json file of a YouTube video is usually 1 to 2 MB, mostly the URLs
// of its formats and automatic captions. Some sites also list the fragments
// of each format, which can add a few megabytes for a long video. A larger
// file is most likely not an .info.json file, and isn't worth reading.
const MAX_INFO_JSON_SIZE = 10_000_000;

/**
 * Read the metadata that yt-dlp wrote with --write-info-json for a video.
 *
 * The server validates the fields, this only rejects files that clearly are
 * not the metadata of a single video.
 *
 * @param {File} file
 * @returns {Promise<object>} The fields of INFO_FIELDS that the file has.
 */
async function readInfoJson(file) {
	if (file.size > MAX_INFO_JSON_SIZE) {
		throw new Error("This file is too large to be an .info.json file");
	}

	const text = await file.text();
	let info;
	try {
		info = JSON.parse(text);
	} catch {
		throw new Error("This file is not valid JSON");
	}

	if (info === null || typeof info !== "object" || Array.isArray(info)) {
		throw new Error("This file does not contain a JSON object");
	}
	if (typeof info.extractor_key !== "string") {
		throw new Error("This file is not an .info.json file written by yt-dlp");
	}
	if ((info._type ?? "video") !== "video") {
		throw new Error("This file describes a playlist, not a single video");
	}

	return Object.fromEntries(
		INFO_FIELDS.filter((field) => field in info).map((field) => [
			field,
			info[field],
		]),
	);
}

export { INFO_FIELDS, MAX_INFO_JSON_SIZE, readInfoJson };
