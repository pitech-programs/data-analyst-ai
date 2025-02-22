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
	let useLocalModel = false;
	let analysisPrompt = 'What is the most expensive brand?';
	let currentStatus = 'Waiting for files...';
	let aiMessage = '';
	let downloadableFiles = [];
	let analysisClient;
	let isAnalyzing = false;
	let messageContainer;

	$: console.log(aiMessage);

	onMount(() => {
		analysisClient = new AnalysisClient();
		analysisClient.connect();
	});

	onDestroy(() => {
		if (analysisClient) {
			analysisClient.disconnect();
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
		downloadableFiles = [];
		currentStatus = 'Starting analysis...';

		try {
			await analysisClient.analyzeFiles(selectedFiles, useLocalModel, analysisPrompt, {
				onError: (error) => {
					currentStatus = `Error: ${error}`;
					isAnalyzing = false;
				},
				onStatus: (status) => {
					currentStatus = status;
					if (status === 'Analysis completed') {
						isAnalyzing = false;
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
				onComplete: () => {
					// Mock downloadable files for now
					downloadableFiles = [
						{ name: 'analysis_report.pdf', url: '#' },
						{ name: 'data_visualization.png', url: '#' }
					];
				}
			});
		} catch (error) {
			currentStatus = `Error: ${error.message}`;
			isAnalyzing = false;
		}
	}
</script>

<div class="min-h-screen bg-gray-900 text-gray-100 p-8">
	<h1 class="text-4xl font-bold text-center mb-8 text-blue-400">Data Analysis Dashboard</h1>

	<div class="grid grid-cols-2 gap-6 max-w-7xl mx-auto">
		<!-- File Upload Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg">
			<h2 class="text-xl font-semibold mb-4">Upload Files</h2>
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
								<span class="truncate">{file.name}</span>
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
			<h2 class="text-xl font-semibold mb-4">AI Status</h2>
			<div bind:this={messageContainer} class="h-[300px] overflow-y-auto space-y-2 relative">
				<div
					class="sticky top-0 inset-x-0 h-16 bg-gradient-to-b from-gray-800/90 via-gray-800/30 to-transparent pointer-events-none backdrop-blur-[2px] z-10"
				></div>
				{#if aiMessage}
					<div class="relative pt-4">
						<div
							class="text-gray-300 animate-fade-in prose prose-invert prose-headings:text-blue-400 prose-h3:text-2xl prose-h3:font-semibold prose-h3:mt-6 prose-p:my-4 prose-p:whitespace-pre-line max-w-none"
						>
							{@html marked.parse(aiMessage)}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Analysis Controls Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg">
			<h2 class="text-xl font-semibold mb-4">Analysis Controls</h2>
			<div class="space-y-6">
				<div class="flex items-center space-x-3">
					<input
						type="checkbox"
						id="privacyToggle"
						bind:checked={useLocalModel}
						class="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
					/>
					<label for="privacyToggle" class="text-gray-300">
						Use Local LLM for Enhanced Privacy
					</label>
				</div>

				<div class="space-y-2">
					<label for="analysisPrompt" class="block text-sm font-medium text-gray-300">
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
					class="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
					on:click={startAnalysis}
					disabled={isAnalyzing || selectedFiles.length === 0}
				>
					{isAnalyzing ? 'Analyzing...' : 'Start Analysis'}
				</button>
			</div>
		</div>

		<!-- Results Section -->
		<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg">
			<h2 class="text-xl font-semibold mb-4">Results</h2>
			<div class="mb-4">
				<p class="text-lg text-blue-400">{currentStatus}</p>
			</div>

			{#if downloadableFiles.length > 0}
				<div class="space-y-3">
					{#each downloadableFiles as file}
						<div class="flex items-center justify-between bg-gray-700 rounded-lg p-3">
							<span class="text-gray-300">{file.name}</span>
							<button class="px-4 py-1 bg-blue-600 hover:bg-blue-700 rounded-md transition-colors">
								Download
							</button>
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-gray-500 text-center py-8">Analysis results will appear here</p>
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
</style>
