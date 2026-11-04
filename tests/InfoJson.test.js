import { describe, expect, it, vi } from "vitest";
import {
	INFO_FIELDS,
	MAX_INFO_JSON_SIZE,
	readInfoJson,
} from "../video2commons/frontend/static/InfoJson.js";

// The fields that the description uses, as in an .info.json file of YouTube.
const YOUTUBE_FIELDS = {
	_type: "video",
	id: "abcdefghijk",
	title: "Example video",
	description: "An example.",
	uploader: "Example channel",
	uploader_url: "https://www.youtube.com/@example",
	upload_date: "20240102",
	license: "Creative Commons Attribution license (reuse allowed)",
	webpage_url: "https://www.youtube.com/watch?v=abcdefghijk",
	extractor: "youtube",
	extractor_key: "Youtube",
};

/**
 * A file chosen by the user.
 *
 * @param {string} text
 * @returns {File}
 */
function jsonFile(text) {
	return new File([text], "Example video [abcdefghijk].info.json", {
		type: "application/json",
	});
}

/**
 * A file of a given size, without its content in memory.
 *
 * @param {number} size
 * @param {string} text What reading it returns.
 * @returns {{ size: number, text: import("vitest").Mock }}
 */
function sizedFile(size, text) {
	return { size, text: vi.fn(async () => text) };
}

describe("readInfoJson", () => {
	it("reads the fields that the description uses", async () => {
		const file = jsonFile(
			JSON.stringify({
				...YOUTUBE_FIELDS,
				formats: [{ url: "https://example.com/video.webm" }],
				thumbnails: [{ url: "https://example.com/thumbnail.jpg" }],
				automatic_captions: { en: [{ url: "https://example.com/en.vtt" }] },
				width: 3840,
				duration: 60,
			}),
		);

		await expect(readInfoJson(file)).resolves.toEqual(YOUTUBE_FIELDS);
	});

	it("names the fields that the server uses", () => {
		expect(INFO_FIELDS).toEqual(Object.keys(YOUTUBE_FIELDS));
	});

	it("leaves out the fields that the file doesn't have", async () => {
		const file = jsonFile(
			JSON.stringify({
				extractor_key: "Generic",
				webpage_url: "https://example.com/video",
			}),
		);

		const info = await readInfoJson(file);

		expect(info).toEqual({
			extractor_key: "Generic",
			webpage_url: "https://example.com/video",
		});
		expect(Object.keys(info)).toEqual(["webpage_url", "extractor_key"]);
	});

	it("keeps the values as they are, for the server to check", async () => {
		const fields = {
			id: 'abcdefghijk" } #',
			title: null,
			description: ["text"],
			uploader: { name: "Example channel" },
			upload_date: 20240102,
			license: true,
			webpage_url: "javascript:alert(1)",
			extractor_key: "Youtube",
		};

		await expect(
			readInfoJson(jsonFile(JSON.stringify(fields))),
		).resolves.toEqual(fields);
	});

	it("reads text in any language", async () => {
		const fields = {
			title: "Vidéo 日本語 🎥",
			description: "Ligne 1\nLigne 2 « citée »",
			extractor_key: "Youtube",
		};

		await expect(
			readInfoJson(jsonFile(JSON.stringify(fields))),
		).resolves.toEqual(fields);
	});

	it("does not inherit fields", async () => {
		// A "__proto__" key of JSON is an ordinary field, which isn't needed.
		const file = jsonFile(
			'{"extractor_key": "Youtube", "__proto__": {"title": "Inherited"}}',
		);

		const info = await readInfoJson(file);

		expect(info).toEqual({ extractor_key: "Youtube" });
		expect(info.title).toBeUndefined();
		expect(Object.getPrototypeOf(info)).toBe(Object.prototype);
	});

	it.each([
		["no type", {}],
		["a null type", { _type: null }],
		["the video type", { _type: "video" }],
	])("accepts a single video with %s", async (_, type) => {
		const fields = { ...type, extractor_key: "Youtube" };

		await expect(
			readInfoJson(jsonFile(JSON.stringify(fields))),
		).resolves.toEqual(fields);
	});

	it.each(["playlist", "multi_video", "url", "url_transparent", "", 1])(
		"rejects the %j type",
		async (type) => {
			const file = jsonFile(
				JSON.stringify({ _type: type, extractor_key: "YoutubeTab" }),
			);

			await expect(readInfoJson(file)).rejects.toThrow(
				"This file describes a playlist, not a single video",
			);
		},
	);

	it.each([
		"",
		"{",
		"not json",
		"{'extractor_key': 'Youtube'}",
		'{"extractor_key": "Youtube",}',
	])("rejects the invalid JSON %j", async (text) => {
		await expect(readInfoJson(jsonFile(text))).rejects.toThrow(
			"This file is not valid JSON",
		);
	});

	it("rejects a binary file", async () => {
		const file = new File(
			[new Uint8Array([0x1a, 0x45, 0xdf, 0xa3, 0, 255])],
			"video.webm",
		);

		await expect(readInfoJson(file)).rejects.toThrow(
			"This file is not valid JSON",
		);
	});

	it.each([
		"null",
		"[]",
		'[{"extractor_key": "Youtube"}]',
		'"text"',
		"1",
		"true",
	])("rejects the JSON value %s", async (text) => {
		await expect(readInfoJson(jsonFile(text))).rejects.toThrow(
			"This file does not contain a JSON object",
		);
	});

	it.each([
		["no extractor_key", undefined],
		["a null extractor_key", null],
		["a numeric extractor_key", 1],
		["an object extractor_key", { name: "Youtube" }],
	])("rejects an object with %s", async (_, extractorKey) => {
		// JSON.stringify() leaves out an undefined extractor_key.
		const file = jsonFile(
			JSON.stringify({ ...YOUTUBE_FIELDS, extractor_key: extractorKey }),
		);

		await expect(readInfoJson(file)).rejects.toThrow(
			"This file is not an .info.json file written by yt-dlp",
		);
	});

	it("checks the extractor_key before the type", async () => {
		const file = jsonFile(JSON.stringify({ _type: "playlist" }));

		await expect(readInfoJson(file)).rejects.toThrow(
			"This file is not an .info.json file written by yt-dlp",
		);
	});

	it("reads a file of the maximum size", async () => {
		const file = sizedFile(MAX_INFO_JSON_SIZE, '{"extractor_key": "Youtube"}');

		await expect(readInfoJson(file)).resolves.toEqual({
			extractor_key: "Youtube",
		});
		expect(file.text).toHaveBeenCalledOnce();
	});

	it("rejects a larger file without reading it", async () => {
		const file = sizedFile(
			MAX_INFO_JSON_SIZE + 1,
			'{"extractor_key": "Youtube"}',
		);

		await expect(readInfoJson(file)).rejects.toThrow(
			"This file is too large to be an .info.json file",
		);
		expect(file.text).not.toHaveBeenCalled();
	});

	it("fails with the error of a file that cannot be read", async () => {
		// E.g. a file deleted after it was chosen.
		const error = new DOMException(
			"The file could not be read.",
			"NotReadableError",
		);
		const file = { size: 10, text: vi.fn(async () => Promise.reject(error)) };

		await expect(readInfoJson(file)).rejects.toBe(error);
	});
});
