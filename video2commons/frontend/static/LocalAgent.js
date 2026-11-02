/** Recognize only individual YouTube video URLs, including Shorts and mobile links. */
export function youtubeVideoUrl(value) {
	try {
		const url = new URL(value.trim());
		if (
			!["http:", "https:"].includes(url.protocol) ||
			url.username ||
			url.password
		)
			return null;
		let id;
		if (url.hostname === "youtu.be") {
			id = url.pathname.replace(/^\/+|\/+$/g, "");
		} else if (
			[
				"youtube.com",
				"www.youtube.com",
				"m.youtube.com",
				"music.youtube.com",
				"youtube-nocookie.com",
				"www.youtube-nocookie.com",
			].includes(url.hostname)
		) {
			id =
				url.pathname === "/watch"
					? url.searchParams.get("v")
					: url.pathname.match(/^\/(?:shorts|embed|live|v)\/([^/]+)\/?$/)?.[1];
		}
		return /^[A-Za-z0-9_-]{11}$/.test(id || "")
			? `https://www.youtube.com/watch?v=${id}`
			: null;
	} catch {
		return null;
	}
}

/** A browser session owns the transfer; the desktop agent gets a separate capability. */
export class LocalAgentTransfer {
	constructor({
		csrfToken,
		onPair,
		onUpdate,
		onReady,
		onError,
		pollInterval = 2000,
	}) {
		Object.assign(this, {
			csrfToken,
			onPair,
			onUpdate,
			onReady,
			onError,
			pollInterval,
		});
		this.controller = new AbortController();
		this.jobId = null;
		this.finished = false;
	}

	async request(endpoint, fields = {}, signal = this.controller.signal) {
		const body = new URLSearchParams({
			...fields,
			_csrf_token: this.csrfToken,
		});
		const response = await fetch(`api/local-agent/${endpoint}`, {
			method: "POST",
			body,
			signal,
		});
		const data = await response.json();
		if (!response.ok || data.error)
			throw new Error(data.error || `HTTP ${response.status}`);
		return data;
	}

	async start(source) {
		try {
			// Do not abort the start request: if cancellation wins the race, we still
			// need its ID to revoke the server-side capability it just created.
			const job = await this.request("start", source, null);
			this.jobId = job.id;
			if (this.controller.signal.aborted) {
				await this.revoke();
				return;
			}
			const base = new URL(".", window.location.href).href.replace(/\/$/, "");
			this.onPair(`${base}#${job.code}`);
			while (!this.controller.signal.aborted) {
				const status = await this.request("status", { id: job.id });
				if (status.state === "error") throw new Error(status.error);
				this.onUpdate(status);
				if (status.state === "ready") {
					this.finished = true;
					this.onReady(status.metadata);
					return;
				}
				await this.sleep();
			}
		} catch (error) {
			if (!this.controller.signal.aborted) {
				this.onError(error.message);
				await this.revoke();
			}
		}
	}

	sleep() {
		return new Promise((resolve) => {
			const done = () => {
				clearTimeout(timer);
				this.controller.signal.removeEventListener("abort", done);
				resolve();
			};
			const timer = setTimeout(done, this.pollInterval);
			this.controller.signal.addEventListener("abort", done, { once: true });
		});
	}

	async revoke() {
		if (!this.jobId || this.finished) return;
		const id = this.jobId;
		this.jobId = null;
		try {
			await this.request("cancel", { id }, null);
		} catch {
			// The server also expires the capability and revokes it on logout.
		}
	}

	cancel() {
		this.controller.abort();
		return this.revoke();
	}
}
