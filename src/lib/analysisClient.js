export class AnalysisClient {
	constructor() {
		this.ws = null;
		this.isConnected = false;
		this.reconnectAttempts = 0;
		this.maxReconnectAttempts = 5;
		this.reconnectDelay = 1000; // Start with 1 second
	}

	connect() {
		if (this.ws?.readyState === WebSocket.OPEN) return;

		this.ws = new WebSocket('ws://localhost:8000/ws/analyze');

		this.ws.onopen = () => {
			this.isConnected = true;
			this.reconnectAttempts = 0;
			this.reconnectDelay = 1000;
			console.log('Connected to analysis server');
		};

		this.ws.onclose = () => {
			this.isConnected = false;
			console.log('Disconnected from analysis server');
			this.tryReconnect();
		};

		this.ws.onerror = (error) => {
			console.error('WebSocket error:', error);
			this.isConnected = false;
		};
	}

	tryReconnect() {
		if (this.reconnectAttempts >= this.maxReconnectAttempts) {
			console.error('Max reconnection attempts reached');
			return;
		}

		setTimeout(() => {
			console.log(
				`Attempting to reconnect (${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})...`
			);
			this.reconnectAttempts++;
			this.reconnectDelay *= 2; // Exponential backoff
			this.connect();
		}, this.reconnectDelay);
	}

	disconnect() {
		if (this.ws) {
			this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect
			this.ws.close();
			this.ws = null;
		}
	}

	async analyzeFiles(files, prompt, callbacks = {}) {
		const connectAndWait = async () => {
			if (!this.isConnected) {
				this.connect();
				// Wait for connection with timeout
				await Promise.race([
					new Promise((resolve) => {
						const checkConnection = setInterval(() => {
							if (this.isConnected) {
								clearInterval(checkConnection);
								resolve();
							}
						}, 100);
					}),
					new Promise((_, reject) => {
						setTimeout(() => {
							reject(new Error('Connection timeout'));
						}, 5000);
					})
				]);
			}
		};

		try {
			await connectAndWait();

			// Send initial analysis request
			const message = {
				type: 'analysis_start',
				fileNames: Array.from(files).map((f) => f.name),
				prompt
			};
			this.ws.send(JSON.stringify(message));

			// Send each file in chunks
			for (const file of files) {
				await this.sendFileInChunks(file);
			}

			// Send analysis complete message
			this.ws.send(JSON.stringify({ type: 'analysis_ready' }));

			// Set up message handling
			this.ws.onmessage = (event) => {
				const response = JSON.parse(event.data);

				if (response.type === 'chunk_received') {
					// Handle chunk acknowledgment
					return;
				}

				if (response.error) {
					callbacks.onError?.(response.error);
				} else if (response.status) {
					callbacks.onStatus?.(response.status);
					if (response.status === 'completed') {
						callbacks.onComplete?.({
							htmlContent: response.html_content,
							pdfContent: response.pdf_content,
							imageData: response.image_data
						});
					}
				} else if (response.content) {
					callbacks.onContent?.(response.content);
				}
			};
		} catch (error) {
			callbacks.onError?.(error.message);
			throw error;
		}
	}

	async readFileContent(file) {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();

			reader.onload = (e) => {
				resolve(e.target.result);
			};

			reader.onerror = (error) => {
				reject(error);
			};

			if (file.name.endsWith('.csv') || file.name.endsWith('.txt')) {
				reader.readAsText(file);
			} else if (file.name.endsWith('.xlsx')) {
				reader.readAsBinaryString(file);
			} else {
				reader.readAsText(file);
			}
		});
	}

	async sendFileInChunks(file) {
		const CHUNK_SIZE = 1024 * 1024; // 1MB chunks
		const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

		for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
			const start = chunkIndex * CHUNK_SIZE;
			const end = Math.min(start + CHUNK_SIZE, file.size);
			const chunk = file.slice(start, end);

			const chunkContent = await new Promise((resolve, reject) => {
				const reader = new FileReader();
				reader.onload = (e) => resolve(e.target.result);
				reader.onerror = reject;

				if (file.name.endsWith('.csv') || file.name.endsWith('.txt')) {
					reader.readAsText(chunk);
				} else if (file.name.endsWith('.xlsx')) {
					reader.readAsBinaryString(chunk);
				} else {
					reader.readAsText(chunk);
				}
			});

			const message = {
				type: 'file_chunk',
				fileName: file.name,
				chunkIndex,
				totalChunks,
				content: chunkContent,
				isLastChunk: chunkIndex === totalChunks - 1
			};

			this.ws.send(JSON.stringify(message));

			// Wait for server acknowledgment before sending next chunk
			await new Promise((resolve) => {
				const handler = (event) => {
					const response = JSON.parse(event.data);
					if (
						response.type === 'chunk_received' &&
						response.fileName === file.name &&
						response.chunkIndex === chunkIndex
					) {
						this.ws.removeEventListener('message', handler);
						resolve();
					}
				};
				this.ws.addEventListener('message', handler);
			});
		}
	}
}
