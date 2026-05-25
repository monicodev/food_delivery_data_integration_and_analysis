# Task 4: Image Processing POC - Technique & Methodology

## 1. Technique Chosen: CLIP (Contrastive Language-Image Pretraining)

For this Proof of Concept (POC), we have implemented a zero-shot image classification approach using **OpenAI's CLIP** model. 

### Why CLIP?
- **Zero-Shot Capability**: Unlike traditional CNNs (like ResNet or VGG) that require training on specific categories, CLIP can classify images into any set of text labels provided at inference time. This is ideal for food identification where the taxonomy might evolve.
- **CPU-Friendly**: While heavy, we use a lightweight implementation suitable for running on standard hardware without requiring high-end GPUs.
- **Semantic Alignment**: CLIP learns visual representations that are semantically aligned with natural language, making it excellent at distinguishing between complex food categories (e.					e.g., "sushi" vs "nigiri") based solely on text prompts.

## 2. Evaluation Methodology

Our evaluation strategy focuses on the accuracy of identifying target food classes within a provided dataset of images.

### Metrics
- **Top-1 Accuracy**: The frequency with which the highest probability prediction matches the ground truth label.
- **Inference Latency**: Time taken to process a single image, ensuring the system remains responsive for real-time pipelines.

### Process
1. **Dataset Preparation**: Use a controlled set of images (from `source/google_images/`) representing various food types.
2. **Prompt Engineering**: Constructing prompts like `"a photo of [food_category]"` to maximize CLIP's performance.
    3. **Automated Scoring**: Comparing the model's prediction against known labels and logging results in a JSON format for auditability.

## 3. Limitations

- **Computational Overhead**: While "CPU-friendly", processing large batches of high-resolution images with CLIP is still significantly slower than traditional lightweight CNNs.
- **Textual Bias**: The accuracy is highly dependent on the quality of the text prompts used during inference.
- **Resolution Constraints**: Standard CLIP models often resize inputs to 224x224, which may lose fine-grained details in complex food textures.
- **Domain Specificity**: While excellent at general objects, its performance on very specific or niche culinary items might require fine-tuning for production-grade accuracy.

## 4. Benchmark Results

> **Note**: Live benchmark numbers require the `torch` and `transformers` packages to be installed
> (`pip install torch transformers`). The `requirements-lock.txt` lists these as optional dependencies
> due to their size (~1.5GB). Below is what the benchmark reports when run:

When executed with a ground-truth dictionary mapping CID → label, the evaluation returns:
- `total_images` — number of images processed
- `top1_accuracy` — fraction where top prediction matches ground truth
- `top3_accuracy` — fraction where ground truth is in top-3 predictions
- `mean_confidence` — average confidence of top predictions
- `mean_latency_ms` — average inference time per image (CPU)
- `p95_latency_ms` — 95th percentile latency

Without ground truth, the latency benchmark reports `mean_latency_ms`, `p95_latency_ms`, `min_latency_ms`, and `max_latency_ms`.

Expected performance for `openai/clip-vit-base-patch32` on a modern CPU (2023+):
- Single image: ~200–500ms on CPU
- Batch of 10: ~150–300ms per image (amortized)
- Memory: ~600–800MB during inference
