import { afterEach, describe, expect, it, vi } from "vitest";
import {
	LocalAgentTransfer,
	youtubeVideoUrl,
} from "../video2commons/frontend/static/LocalAgent.js";

const url = "https://www.youtube.com/watch?v=abcdefghijk";

afterEach(() => {
	vi.unstubAllGlobals();
	vi.useRealTimers();
});

describe("YouTube local agent offer", () => {
	it.each([
		url,
		"https://youtu.be/abcdefghijk?t=3",
		"https://m.youtube.com/watch?v=abcdefghijk&list=123",
		"https://youtube.com/shorts/abcdefghijk",
		"https://youtube.com/live/abcdefghijk",
		"https://www.youtube-nocookie.com/embed/abcdefghijk",
	])("recognizes individual video link %s", (value) => {
		expect(youtubeVideoUrl(value)).toBe(url);
	});

	it.each([
		"https://youtube.com.evil.test/watch?v=abcdefghijk",
		"https://youtube.com/playlist?list=123",
		"https://evil.test/watch?v=abcdefghijk",
		"https://user@youtube.com/watch?v=abcdefghijk",
		"javascript:alert(1)",
		"https://youtube.com/watch?v=short",
		"",
	])("does not offer a transfer for %s", (value) => {
		expect(youtubeVideoUrl(value)).toBeNull();
	});
});

function setup(responses) {
	vi.stubGlobal("window", {
		location: { href: "https://video2commons.toolforge.org/" },
	});
	const fetch = vi.fn(async () => {
		const result = responses.shift();
		if (result instanceof Error) throw result;
		return { ok: !result.error, json: async () => result };
	});
	vi.stubGlobal("fetch", fetch);
	const callbacks = {
		onPair: vi.fn(),
		onUpdate: vi.fn(),
		onReady: vi.fn(),
		onError: vi.fn(),
	};
	const transfer = new LocalAgentTransfer({
		csrfToken: "csrf",
		pollInterval: 1,
		...callbacks,
	});
	return { transfer, callbacks, fetch };
}

describe("local agent browser lifecycle", () => {
	it("pairs, polls and hands staged metadata to the normal wizard", async () => {
		const metadata = {
			url: "uploads:file.webm",
			filedesc: "source and license",
		};
		const { transfer, callbacks, fetch } = setup([
			{ id: "job", code: "pairing" },
			{ state: "waiting" },
			{ state: "downloading" },
			{ state: "uploading", percent: 40 },
			{ state: "ready", metadata },
		]);
		await transfer.start({ url, video: true, audio: true });
		expect(callbacks.onPair).toHaveBeenCalledWith(
			"https://video2commons.toolforge.org#pairing",
		);
		expect(callbacks.onReady).toHaveBeenCalledWith(metadata);
		expect(callbacks.onError).not.toHaveBeenCalled();
		for (const [, options] of fetch.mock.calls) {
			expect(options.body.get("_csrf_token")).toBe("csrf");
		}
		await transfer.cancel();
		expect(
			fetch.mock.calls.some(([endpoint]) => endpoint.endsWith("cancel")),
		).toBe(false);
	});

	it("revokes the transfer and reports agent or network errors", async () => {
		const { transfer, callbacks, fetch } = setup([
			{ id: "job", code: "pairing" },
			{ state: "error", error: "YouTube blocked this download" },
			{ cancelled: true },
		]);
		await transfer.start({ url });
		expect(callbacks.onError).toHaveBeenCalledWith(
			"YouTube blocked this download",
		);
		expect(fetch.mock.calls.at(-1)[0]).toBe("api/local-agent/cancel");
		expect(callbacks.onReady).not.toHaveBeenCalled();
	});

	it("revokes a transfer even when cancelled before start returns", async () => {
		const { transfer, callbacks, fetch } = setup([]);
		let finishStart;
		fetch.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finishStart = resolve;
				}),
		);
		fetch.mockResolvedValueOnce({
			ok: true,
			json: async () => ({ cancelled: true }),
		});
		const started = transfer.start({ url });
		await transfer.cancel();
		finishStart({
			ok: true,
			json: async () => ({ id: "job", code: "pairing" }),
		});
		await started;
		expect(fetch.mock.calls.at(-1)[0]).toBe("api/local-agent/cancel");
		expect(callbacks.onPair).not.toHaveBeenCalled();
		expect(callbacks.onReady).not.toHaveBeenCalled();
		expect(callbacks.onError).not.toHaveBeenCalled();
	});

	it("stops polling when the dialog is closed", async () => {
		const { transfer, callbacks, fetch } = setup([
			{ id: "job", code: "pairing" },
			{ state: "waiting" },
			{ cancelled: true },
		]);
		callbacks.onUpdate.mockImplementation(() => {
			transfer.cancel();
		});
		await transfer.start({ url });
		expect(callbacks.onUpdate).toHaveBeenCalledTimes(1);
		expect(fetch.mock.calls.at(-1)[0]).toBe("api/local-agent/cancel");
		expect(callbacks.onReady).not.toHaveBeenCalled();
	});
});
