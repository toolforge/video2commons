import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChunkedUploader } from "../video2commons/frontend/static/ChunkedUploader.js";
import { awaitDone, awaitEvent, collectEvents } from "./helpers.js";
import {
	createUploadHandler,
	server,
	UPLOAD_ENDPOINT,
} from "./mocks/backend.js";

describe("ChunkedUploader", () => {
	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	it("uploads a small single-chunk file without a Content-Range header", async () => {
		const { handler, requests, filekey } = createUploadHandler();
		server.use(handler);

		const file = new File([new Uint8Array(100)], "tiny.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 1000,
		});

		const progressEvents = collectEvents(uploader, "progress");

		uploader.start();
		const result = await awaitDone(uploader);

		expect(result.filekey).toBe(filekey);
		expect(requests).toHaveLength(1);
		expect(requests[0].headers.get("Content-Range")).toBeNull();
		expect(progressEvents).toHaveLength(1);
		expect(progressEvents[0].detail).toEqual({
			percent: 100,
			loaded: 100,
			total: 100,
		});
	});

	it("uploads a three-chunk file with correct Content-Range sequencing", async () => {
		const { handler, requests, filekey } = createUploadHandler();
		server.use(handler);

		// 250 bytes at 100 bytes/chunk in chunks of 100, 100, 50.
		const file = new File([new Uint8Array(250)], "multi.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
		});

		const progressEvents = collectEvents(uploader, "progress");

		uploader.start();
		const result = await awaitDone(uploader);

		expect(result.filekey).toBe(filekey);
		expect(requests).toHaveLength(3);
		expect(requests[0].headers.get("Content-Range")).toBe("bytes 0-99/250");
		expect(requests[1].headers.get("Content-Range")).toBe("bytes 100-199/250");
		expect(requests[2].headers.get("Content-Range")).toBe("bytes 200-249/250");
		expect(progressEvents.map((e) => e.detail.loaded)).toEqual([100, 200, 250]);
		expect(progressEvents.at(-1).detail.percent).toBe(100);
	});

	it("uploads a 10-chunk file with an offline interruption lasting longer than the timeout", async () => {
		vi.useFakeTimers();

		const { handler, requests, filekey, setOffline } = createUploadHandler();
		server.use(handler);

		// 1000 bytes at 100 bytes/chunk = 10 chunks.
		const file = new File([new Uint8Array(1000)], "ten.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			chunkTimeout: 120_000,
		});

		// Flipping the offline flag from the listener lands the uploader in a
		// "paused" state before chunk 4's fetch is sent.
		const progressEvents = collectEvents(uploader, "progress");
		uploader.addEventListener("progress", () => {
			if (progressEvents.length === 3) {
				setOffline(true);
			}
		});

		const onlineEvents = collectEvents(uploader, "online");
		const errorEvents = collectEvents(uploader, "error");

		uploader.start();
		await awaitEvent(uploader, "offline");

		// Advance well past the default chunkTimeout (120s) to prove a paused
		// uploader neither errors out nor issues further requests while offline.
		await vi.advanceTimersByTimeAsync(200_000);

		expect(errorEvents).toHaveLength(0);
		expect(requests).toHaveLength(3);
		expect(progressEvents.at(-1).detail).toEqual({
			percent: 30,
			loaded: 300,
			total: 1000,
		});

		// Restore connectivity; the pending chunk is re-sent from the same
		// offset, and the remaining chunks follow.
		setOffline(false);

		const result = await awaitDone(uploader);

		expect(result.filekey).toBe(filekey);
		expect(requests).toHaveLength(10);
		expect(onlineEvents).toHaveLength(1);
		expect(progressEvents.at(-1).detail).toEqual({
			percent: 100,
			loaded: 1000,
			total: 1000,
		});
	});

	it("handles retries gracefully and completes the upload", async () => {
		const { handler, requests, filekey } = createUploadHandler();

		// Fail the second POST once with a retryable 5xx, then let the retry
		// fall through to the main handler and succeed.
		let seen = 0;
		const flakyHandler = http.post(UPLOAD_ENDPOINT, () => {
			seen++;
			if (seen === 2) {
				return new HttpResponse("Service Unavailable", { status: 503 });
			}
		});

		server.use(flakyHandler, handler);

		// 250 bytes at 100 bytes/chunk = 3 chunks.
		const file = new File([new Uint8Array(250)], "flaky.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			maxAttempts: 4,
			retryDelay: 10,
		});

		const retryEvents = collectEvents(uploader, "retry");

		uploader.start();
		const result = await awaitDone(uploader);

		expect(result.filekey).toBe(filekey);
		expect(requests).toHaveLength(3);
		expect(retryEvents).toHaveLength(1);
		expect(retryEvents[0].detail).toEqual({
			chunk: 1,
			attempt: 2,
			maxAttempts: 4,
			error: "Server error (503)",
		});
	});

	it("gives up after running out of retries for a chunk", async () => {
		const { handler, requests } = createUploadHandler();

		// Let chunk 0 through, then fail every subsequent POST.
		let seen = 0;
		const alwaysFailHandler = http.post(UPLOAD_ENDPOINT, () => {
			seen++;
			if (seen >= 2) {
				return new HttpResponse("Service Unavailable", { status: 503 });
			}
		});

		server.use(alwaysFailHandler, handler);

		// 250 bytes at 100 bytes/chunk = 3 chunks.
		const file = new File([new Uint8Array(250)], "broken.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			maxAttempts: 3,
			retryDelay: 10,
		});

		const retryEvents = collectEvents(uploader, "retry");

		uploader.start();
		const errorEvent = await awaitEvent(uploader, "error");

		// 3 attempts on chunk 1 means 2 retry events, for attempts 2 and 3.
		expect(retryEvents).toHaveLength(2);
		expect(retryEvents.map((e) => e.detail.attempt)).toEqual([2, 3]);
		expect(errorEvent.detail).toEqual({
			type: "failure",
			message: "Server error (503)",
			chunk: 1,
		});
		// Only chunk 0 reached the main handler successfully.
		expect(requests).toHaveLength(1);
	});

	it("resets retries for subsequent chunks", async () => {
		const { handler, requests, filekey } = createUploadHandler();

		// Fail chunks 1 and 2 twice each before letting them through. With
		// maxAttempts: 3, both chunks need their full retry budget if the
		// budget weren't reset between chunks, chunk 2 would error out.
		let seen = 0;
		const flakyHandler = http.post(UPLOAD_ENDPOINT, () => {
			seen++;
			// Chunk 0 succeeds on request 1; chunk 1 retries on requests 2-3
			// and succeeds on request 4; chunk 2 retries on requests 5-6 and
			// succeeds on request 7.
			if ([2, 3, 5, 6].includes(seen)) {
				return new HttpResponse("Service Unavailable", { status: 503 });
			}
		});

		server.use(flakyHandler, handler);

		// 300 bytes at 100 bytes/chunk = 3 chunks.
		const file = new File([new Uint8Array(300)], "resets.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			maxAttempts: 3,
			retryDelay: 10,
		});

		const retryEvents = collectEvents(uploader, "retry");

		uploader.start();
		const result = await awaitDone(uploader);

		expect(result.filekey).toBe(filekey);
		expect(requests).toHaveLength(3);
		expect(retryEvents.map((e) => e.detail)).toEqual([
			{ chunk: 1, attempt: 2, maxAttempts: 3, error: "Server error (503)" },
			{ chunk: 1, attempt: 3, maxAttempts: 3, error: "Server error (503)" },
			{ chunk: 2, attempt: 2, maxAttempts: 3, error: "Server error (503)" },
			{ chunk: 2, attempt: 3, maxAttempts: 3, error: "Server error (503)" },
		]);
	});

	it("should treat 4xx errors as fatal and do not retry", async () => {
		const { handler, requests } = createUploadHandler();

		// Let chunk 0 through, then fail chunk 1 with a 4xx.
		let seen = 0;
		const badRequestHandler = http.post(UPLOAD_ENDPOINT, () => {
			seen++;
			if (seen === 2) {
				return new HttpResponse("Bad Request", { status: 400 });
			}
		});

		server.use(badRequestHandler, handler);

		// 250 bytes at 100 bytes/chunk = 3 chunks.
		const file = new File([new Uint8Array(250)], "fatal.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			maxAttempts: 4,
			retryDelay: 10,
		});

		const retryEvents = collectEvents(uploader, "retry");

		uploader.start();
		const errorEvent = await awaitEvent(uploader, "error");

		expect(retryEvents).toHaveLength(0);
		expect(errorEvent.detail).toEqual({
			type: "failure",
			message: "Server error (400)",
			chunk: 1,
		});
		// Only chunk 0 reached the main handler.
		expect(requests).toHaveLength(1);
	});

	it("errors when a chunk exceeds chunkTimeout", async () => {
		vi.useFakeTimers();

		// AbortSignal.timeout doesn't use vitest's fake timers. Reroute it
		// through globalThis.setTimeout so vitest can drive it.
		vi.spyOn(AbortSignal, "timeout").mockImplementation((ms) => {
			const ctrl = new AbortController();
			setTimeout(
				() => ctrl.abort(new DOMException("signal timed out", "TimeoutError")),
				ms,
			);
			return ctrl.signal;
		});

		const { handler, requests } = createUploadHandler();

		// First POST hangs forever so AbortSignal.timeout has to fire.
		const hangingHandler = http.post(
			UPLOAD_ENDPOINT,
			() => new Promise(() => {}),
			{ once: true },
		);

		server.use(hangingHandler, handler);

		// 200 bytes at 100 bytes/chunk = 2 chunks.
		const file = new File([new Uint8Array(200)], "slow.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			chunkTimeout: 5_000,
			maxAttempts: 1,
		});

		const errorPromise = awaitEvent(uploader, "error");

		uploader.start();
		await vi.advanceTimersByTimeAsync(5_000);

		const errorEvent = await errorPromise;
		expect(errorEvent.detail.chunk).toBe(0);
		// The hanging handler intercepted before the main handler ever saw it.
		expect(requests).toHaveLength(0);
	});

	it("stops cleanly when abort() is called mid-upload", async () => {
		const { handler, requests } = createUploadHandler();
		server.use(handler);

		// 300 bytes at 100 bytes/chunk = 3 chunks.
		const file = new File([new Uint8Array(300)], "abort.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
		});

		// Abort synchronously from the first progress event, before chunk 1
		// has a chance to dispatch.
		const progressEvents = collectEvents(uploader, "progress");
		uploader.addEventListener("progress", () => {
			if (progressEvents.length === 1) uploader.abort();
		});
		const finishEvents = collectEvents(uploader, "finish");

		uploader.start();
		const errorEvent = await awaitEvent(uploader, "error");

		expect(errorEvent.detail).toEqual({
			type: "abort",
			message: "Upload aborted",
			chunk: 1,
		});
		expect(finishEvents).toHaveLength(0);
		// Only chunk 0 went through and the remaining chunks never dispatched.
		expect(requests).toHaveLength(1);
	});

	it("treats a step:error response as fatal and does not retry", async () => {
		const { handler, requests } = createUploadHandler();

		// Let chunk 0 through, then return a backend-level error envelope on
		// chunk 1. The HTTP status is 200 even for errors (yuck).
		let seen = 0;
		const errorEnvelopeHandler = http.post(UPLOAD_ENDPOINT, () => {
			seen++;
			if (seen === 2) {
				return HttpResponse.json({
					step: "error",
					error: "Invalid session",
				});
			}
		});

		server.use(errorEnvelopeHandler, handler);

		// 250 bytes at 100 bytes/chunk = 3 chunks.
		const file = new File([new Uint8Array(250)], "session.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			maxAttempts: 4,
			retryDelay: 10,
		});

		const retryEvents = collectEvents(uploader, "retry");

		uploader.start();
		const errorEvent = await awaitEvent(uploader, "error");

		expect(retryEvents).toHaveLength(0);
		expect(errorEvent.detail).toEqual({
			type: "failure",
			message: "Invalid session",
			chunk: 1,
		});
		// Only chunk 0 reached the main handler.
		expect(requests).toHaveLength(1);
	});

	it("throws when start() is called twice", async () => {
		const { handler } = createUploadHandler();
		server.use(handler);

		const file = new File([new Uint8Array(100)], "twice.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 1000,
		});

		uploader.start();
		expect(() => uploader.start()).toThrow("Upload already started");

		// Let the upload finish so its request doesn't leak into the next test.
		await awaitDone(uploader);
	});

	it("treats a server offset mismatch as fatal", async () => {
		// Backend envelope with a deliberately wrong offset for chunk 0.
		const badOffsetHandler = http.post(
			UPLOAD_ENDPOINT,
			() =>
				HttpResponse.json({
					step: "uploaded",
					result: "Continue",
					offset: 50,
					filekey: "bad-offset",
				}),
			{ once: true },
		);

		server.use(badOffsetHandler);

		// 250 bytes at 100 bytes/chunk = 3 chunks (forces Content-Range path).
		const file = new File([new Uint8Array(250)], "offset.bin");
		const uploader = new ChunkedUploader({
			endpoint: UPLOAD_ENDPOINT,
			file,
			csrfToken: "csrf",
			chunkSize: 100,
			maxAttempts: 4,
			retryDelay: 10,
		});

		const retryEvents = collectEvents(uploader, "retry");

		uploader.start();
		const errorEvent = await awaitEvent(uploader, "error");

		expect(retryEvents).toHaveLength(0);
		expect(errorEvent.detail).toEqual({
			type: "failure",
			message: "Offset mismatch: expected 100, got 50",
			chunk: 0,
		});
	});
});
