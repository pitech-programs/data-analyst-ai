<script>
	import { onMount, onDestroy } from 'svelte';
	import { AnalysisClient } from '$lib/analysisClient';
	import { marked } from 'marked';

	// Configure marked to sanitize HTML by default
	marked.setOptions({
		sanitize: true,
		breaks: true
	});

	let selectedFiles = [];
	let analysisPrompt = 'What is the most expensive brand on average?';
	let currentStatus = 'Waiting for files...';
	let aiMessage = '';
	let htmlContent = '';
	let pdfContent = '';
	let imageData = {};
	let audioContent = '';
	let verbalSummary = '';
	let audioPlayer;
	let isPlaying = false;
	let currentTime = 0;
	let duration = 0;
	let analysisClient;
	let isAnalyzing = false;
	let messageContainer;
	let dots = '';
	let streamingVerbalSummary = '';
	let isGeneratingSummary = false;
	let showTranscript = false;

	// Add interval for animated dots
	let dotsInterval;

	function formatTime(seconds) {
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}

	function handlePlayPause() {
		if (audioPlayer) {
			if (isPlaying) {
				audioPlayer.pause();
			} else {
				audioPlayer.play();
			}
			isPlaying = !isPlaying;
		}
	}

	function handleTimeUpdate(event) {
		currentTime = event.target.currentTime;
	}

	function handleDurationChange(event) {
		duration = event.target.duration;
	}

	function handleSeek(event) {
		if (audioPlayer) {
			const seekTime = event.target.value;
			audioPlayer.currentTime = seekTime;
			currentTime = seekTime;
		}
	}

	onMount(() => {
		analysisClient = new AnalysisClient();
		analysisClient.connect();
	});

	onDestroy(() => {
		if (analysisClient) {
			analysisClient.disconnect();
		}
		if (dotsInterval) {
			clearInterval(dotsInterval);
		}
	});

	function handleFileDrop(e) {
		e.preventDefault();
		const files = Array.from(e.dataTransfer?.files || []);
		if (files.length + selectedFiles.length > 5) {
			alert('Maximum 5 files allowed');
			return;
		}
		selectedFiles = [...selectedFiles, ...files].slice(0, 5);
	}

	function handleFileSelect(e) {
		const files = Array.from(e.target.files || []);
		if (files.length + selectedFiles.length > 5) {
			alert('Maximum 5 files allowed');
			return;
		}
		selectedFiles = [...selectedFiles, ...files].slice(0, 5);
	}

	function openHtmlReport() {
		const blob = new Blob([htmlContent], { type: 'text/html' });
		const url = URL.createObjectURL(blob);

		const a = document.createElement('a');
		a.href = url;
		a.download = 'analysis_report.html';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);

		// Clean up the URL after a delay
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}

	function downloadPdfReport() {
		const binaryContent = atob(pdfContent);
		const bytes = new Uint8Array(binaryContent.length);
		for (let i = 0; i < binaryContent.length; i++) {
			bytes[i] = binaryContent.charCodeAt(i);
		}
		const blob = new Blob([bytes], { type: 'application/pdf' });
		const url = URL.createObjectURL(blob);

		const a = document.createElement('a');
		a.href = url;
		a.download = 'analysis_report.pdf';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);

		// Clean up the URL after a delay
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}

	async function startAnalysis() {
		if (selectedFiles.length === 0) {
			alert('Please select at least one file');
			return;
		}

		if (!analysisPrompt.trim()) {
			alert('Please enter an analysis prompt');
			return;
		}

		isAnalyzing = true;
		aiMessage = '';
		htmlContent = '';
		pdfContent = '';
		currentStatus = 'Starting analysis...';
		dots = '';

		// Start dots animation
		dotsInterval = setInterval(() => {
			dots = dots.length >= 3 ? '' : dots + '.';
		}, 500);

		try {
			await analysisClient.analyzeFiles(selectedFiles, analysisPrompt, {
				onError: (error) => {
					currentStatus = `Error: ${error}`;
					isAnalyzing = false;
					clearInterval(dotsInterval);
				},
				onStatus: (status) => {
					if (status === 'completed') {
						currentStatus = '🎉 Analysis completed successfully! Your reports are ready below.';
						isAnalyzing = false;
						clearInterval(dotsInterval);
					} else {
						currentStatus = status;
					}
				},
				onContent: (content) => {
					aiMessage += content;
					// Scroll to bottom after content update
					if (messageContainer) {
						setTimeout(() => {
							messageContainer.scrollTop = messageContainer.scrollHeight;
						}, 0);
					}
				},
				onVerbalSummaryChunk: (chunk) => {
					streamingVerbalSummary += chunk;
					isGeneratingSummary = true;
				},
				onComplete: ({
					htmlContent: html,
					pdfContent: pdf,
					imageData: images,
					audioContent: audio,
					verbalSummary: summary
				}) => {
					htmlContent = html;
					pdfContent = pdf;
					imageData = images;
					audioContent = audio;
					verbalSummary = summary;
					isGeneratingSummary = false;
				}
			});
		} catch (error) {
			currentStatus = `Error: ${error.message}`;
			isAnalyzing = false;
			clearInterval(dotsInterval);
		}
	}
</script>

<div class="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 text-gray-100 p-8">
	<div class="flex flex-col items-center mb-8">
		<h1
			class="text-5xl font-extrabold text-center bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-blue-500 to-purple-600 drop-shadow-lg tracking-tight pb-2"
		>
			AI Data Analysis Agent
		</h1>
		<p class="text-blue-400 mt-2 text-lg font-medium tracking-wide">
			Your Intelligent Data Companion
		</p>
	</div>

	<div class="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-7xl mx-auto">
		<!-- File Upload Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg">
			<h2 class="text-xl font-semibold mb-4 text-blue-400 uppercase tracking-wide">Upload Files</h2>
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="border-2 border-dashed border-gray-600 rounded-lg p-8 text-center hover:border-blue-500 transition-colors"
				on:dragover|preventDefault
				on:drop={handleFileDrop}
			>
				<input
					type="file"
					id="fileInput"
					multiple
					class="hidden"
					on:change={handleFileSelect}
					accept=".csv,.xlsx,.json,.txt"
				/>
				<label for="fileInput" class="cursor-pointer flex flex-col items-center">
					<svg
						class="w-12 h-12 text-gray-400 mb-4"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
						/>
					</svg>
					<span class="text-gray-300">Drop files here or click to select</span>
					<span class="text-sm text-gray-500 mt-2">Maximum 5 files</span>
				</label>
			</div>
			{#if selectedFiles.length > 0}
				<div class="mt-4">
					<h3 class="text-sm font-medium mb-2">Selected Files:</h3>
					<ul class="space-y-2">
						{#each selectedFiles as file}
							<li class="flex items-center justify-between bg-gray-700 rounded p-2">
								<div class="flex items-center">
									<svg
										class="w-5 h-5 mr-2 text-gray-400"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
										/>
									</svg>
									<span class="truncate">{file.name}</span>
								</div>
								<button
									class="text-red-400 hover:text-red-300"
									on:click={() => (selectedFiles = selectedFiles.filter((f) => f !== file))}
								>
									×
								</button>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		</div>

		<!-- AI Status Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg overflow-hidden">
			<h2 class="text-xl font-semibold mb-4 text-blue-400 uppercase tracking-wide">AI Status</h2>

			<!-- Current Status -->
			<div class="mb-4 p-3 bg-gray-700 rounded-lg">
				<p class="text-blue-400 font-medium flex items-center">
					{#if isAnalyzing}
						<svg
							class="w-5 h-5 mr-2 animate-spin"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
							/>
						</svg>
					{/if}
					{currentStatus}{isAnalyzing ? dots : ''}
				</p>
			</div>

			<!-- AI Message Container -->
			<div bind:this={messageContainer} class="h-[300px] overflow-y-hidden space-y-2 relative">
				<div
					class="sticky top-0 inset-x-0 h-20 bg-gradient-to-b from-gray-800/90 via-gray-800/30 to-transparent pointer-events-none backdrop-blur-[1.3px] z-10"
				></div>
				{#if aiMessage}
					<div class="relative pt-4">
						<div class="text-gray-300 animate-fade-in max-w-none">
							{@html marked.parse(aiMessage, { breaks: true })}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Analysis Controls Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg">
			<h2 class="text-xl font-semibold mb-4 text-blue-400 uppercase tracking-wide">
				Analysis Controls
			</h2>
			<div class="space-y-6">
				<div class="space-y-2">
					<label for="analysisPrompt" class="text-sm font-medium text-gray-300 flex items-center">
						<svg
							class="w-5 h-5 mr-2 text-blue-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
							/>
						</svg>
						Analysis Focus
					</label>
					<textarea
						id="analysisPrompt"
						bind:value={analysisPrompt}
						placeholder="E.g., 'Sales from Q3 2024' or 'Customer demographics analysis'"
						class="w-full h-24 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					></textarea>
				</div>

				<button
					class="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center justify-center space-x-2"
					on:click={startAnalysis}
					disabled={isAnalyzing || selectedFiles.length === 0}
				>
					{#if isAnalyzing}
						<svg class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
							/>
						</svg>
					{/if}
					<span>{isAnalyzing ? 'Analyzing...' : 'Start Analysis'}</span>
				</button>
			</div>
		</div>

		<!-- Results Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg">
			<h2 class="text-xl font-semibold mb-4 text-blue-400 uppercase tracking-wide">Results</h2>

			{#if htmlContent && pdfContent}
				<div class="space-y-4">
					<div class="grid grid-cols-2 gap-4">
						<div class="bg-gray-700 rounded-lg p-4 shadow-md hover:shadow-lg transition-shadow">
							<h3 class="text-lg font-medium mb-2 text-gray-200">Interactive Report</h3>
							<p class="text-sm text-gray-400 mb-4">
								Explore the analysis with interactive charts and tables.
							</p>
							<button
								on:click={openHtmlReport}
								class="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center justify-center space-x-2"
							>
								<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
									/>
								</svg>
								<span>Download HTML Report</span>
							</button>
						</div>
						<div class="bg-gray-700 rounded-lg p-4 shadow-md hover:shadow-lg transition-shadow">
							<h3 class="text-lg font-medium mb-2 text-gray-200">PDF Report</h3>
							<p class="text-sm text-gray-400 mb-4">
								Get a printable version of the analysis report.
							</p>
							<button
								on:click={downloadPdfReport}
								class="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center justify-center space-x-2"
							>
								<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
									/>
								</svg>
								<span>Download PDF Report</span>
							</button>
						</div>
					</div>

					<!-- Audio Player Section -->
					{#if isGeneratingSummary || audioContent}
						<div class="mt-6 bg-gray-700 rounded-lg p-4 shadow-md relative">
							<div class="flex justify-between items-center mb-3">
								<h3 class="text-lg font-medium text-gray-200">Audio Summary</h3>
								{#if audioContent}
									<div class="relative">
										<button
											class="p-1.5 hover:bg-gray-600 rounded-full transition-colors"
											on:click={() => {
												const blob = new Blob(
													[Uint8Array.from(atob(audioContent), (c) => c.charCodeAt(0))],
													{ type: 'audio/mp3' }
												);
												const url = URL.createObjectURL(blob);
												const a = document.createElement('a');
												a.href = url;
												a.download = 'audio_summary.mp3';
												document.body.appendChild(a);
												a.click();
												document.body.removeChild(a);
												setTimeout(() => URL.revokeObjectURL(url), 1000);
											}}
										>
											<svg
												class="w-5 h-5 text-gray-300 hover:text-white"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
												/>
											</svg>
										</button>
									</div>
								{/if}
							</div>

							{#if isGeneratingSummary}
								<div class="space-y-3">
									<!-- Streaming Summary -->
									<div class="flex items-center space-x-2 text-blue-400">
										<svg
											class="w-5 h-5 animate-spin"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
											></path>
										</svg>
										<span>Generating verbal summary...</span>
									</div>
									<div class="mt-4 p-3 bg-gray-800 rounded-lg text-sm text-gray-300">
										<p class="whitespace-pre-line animate-pulse">{streamingVerbalSummary}</p>
									</div>
								</div>
							{:else if audioContent}
								<!-- Hidden Audio Element -->
								<audio
									bind:this={audioPlayer}
									src={`data:audio/mp3;base64,${audioContent}`}
									on:timeupdate={handleTimeUpdate}
									on:durationchange={handleDurationChange}
									on:ended={() => (isPlaying = false)}
									class="hidden"
								></audio>

								<!-- Custom Audio Player UI -->
								<div class="space-y-3">
									<!-- Play/Pause Button and Time Display -->
									<div class="flex items-center justify-between">
										<button
											on:click={handlePlayPause}
											class="p-2 rounded-full bg-blue-600 hover:bg-blue-700 transition-colors"
										>
											{#if isPlaying}
												<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														stroke-width="2"
														d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"
													/>
												</svg>
											{:else}
												<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														stroke-width="2"
														d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
													/>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														stroke-width="2"
														d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
													/>
												</svg>
											{/if}
										</button>
										<div class="flex justify-between text-sm text-gray-300 w-full ml-4">
											<span>{formatTime(currentTime)}</span>
											<span>{formatTime(duration)}</span>
										</div>
									</div>

									<!-- Progress Bar -->
									<input
										type="range"
										min="0"
										max={duration}
										value={currentTime}
										on:input={handleSeek}
										class="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer accent-blue-500"
									/>

									<!-- Transcript Toggle -->
									{#if verbalSummary}
										<button
											on:click={() => (showTranscript = !showTranscript)}
											class="mt-4 text-sm text-blue-400 hover:text-blue-300 transition-colors flex items-center space-x-1"
										>
											<span>{showTranscript ? 'Hide' : 'Show'} Transcript</span>
											<svg
												class="w-4 h-4 transform transition-transform duration-200 {showTranscript
													? 'rotate-180'
													: ''}"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M19 9l-7 7-7-7"
												/>
											</svg>
										</button>

										<!-- Transcript Content with Animation -->
										<div
											class="overflow-y-auto transition-all duration-300 ease-in-out"
											style="max-height: {showTranscript
												? '500px'
												: '0px'}; opacity: {showTranscript ? '1' : '0'}"
										>
											<div class="mt-4 p-3 bg-gray-800 rounded-lg text-sm text-gray-300">
												<p class="whitespace-pre-line">{verbalSummary}</p>
											</div>
										</div>
									{/if}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{:else}
				<div class="text-center py-8">
					<svg
						class="w-16 h-16 mx-auto text-gray-600 mb-4"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
						/>
					</svg>
					<p class="text-gray-500">Start an analysis to see your results here</p>
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.animate-fade-in {
		animation: fadeIn 0.5s ease-in;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	.animate-spin {
		animation: spin 1s linear infinite;
	}
</style>
