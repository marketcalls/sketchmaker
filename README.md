# SketchMaker AI

SketchMaker AI is an advanced AI-powered image generation tool that creates custom images based on user descriptions and preferences. It's designed to produce high-quality, tailored images for various purposes such as social media content, blog posts, marketing materials, and more.

![SketchMaker AI Preview](https://www.marketcalls.in/wp-content/uploads/2024/08/SketchMaker-v2.png)

## Features

- **AI-Powered Image Generation**: Generate unique images based on textual descriptions.
- **Multiple AI Models**: Choose from various AI models including Flux Pro, Flux Lora, Flux Dev, and Flux Realism.
- **Customizable Image Sizes**: Choose from a wide range of preset sizes or specify custom dimensions.
- **Artistic Style Selection**: Apply various artistic styles to your generated images.
- **Color Scheme Options**: Select from different color palettes to match your needs.
- **Lighting and Mood Control**: Adjust the lighting and overall mood of the generated images.
- **Subject Focus**: Specify the main subject of your image for more accurate results.
- **Background Style**: Choose from various background styles to complement your image.
- **Effects and Filters**: Apply different effects and filters to enhance your image.
- **Advanced Parameters**: Fine-tune your image generation with adjustable inference steps, guidance scale, and seed value.
- **LoRA Support**: Use custom LoRA models for even more specialized image generation (available with Flux Lora model).
- **Enhanced Prompt Generation**: Automatically enhance your input prompts for better image results.
- **Multi-Format Downloads**: Download your images in WebP, PNG, and JPEG formats.
- **Image Gallery**: Browse your generated images.
- **User-Friendly Interface**: Easy-to-use web interface built with modern design principles.

![SketchMaker Generated Image](https://www.marketcalls.in/wp-content/uploads/2024/08/Traders-Reading-News-and-Freaking-out.png)

## Capabilities and Use Cases

SketchMaker AI is a versatile tool that can be used in various scenarios:

1. **Marketing and Advertising**: Create eye-catching visuals for social media posts, ads, and marketing campaigns.
2. **Content Creation**: Generate unique illustrations for blog posts, articles, and e-books.
3. **Product Design**: Visualize product concepts and create mockups quickly.
4. **Branding**: Design logos, brand assets, and visual identity elements.
5. **Education**: Produce educational materials, infographics, and visual aids.
6. **Gaming and Entertainment**: Create character concepts, environment designs, and promotional artwork.
7. **Web Design**: Generate custom graphics, icons, and UI elements for websites and apps.
8. **Personal Projects**: Bring your creative ideas to life, from digital art to personalized gifts.

SketchMaker AI's ability to combine detailed prompts with various artistic styles and parameters allows users to create highly customized images that match their specific needs. The LoRA support further extends this capability, enabling fine-tuned models for specialized use cases.

## Getting Started

### Prerequisites

- Python 3.10+
- Flask
- OpenAI API key
- FAL API key

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/marketcalls/sketchmaker.git
   cd sketchmaker
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Rename the `.env.sample` file to `.env` and add your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   FAL_KEY=your_fal_api_key
   OPENAI_MODEL=your_preferred_openai_model
   ```

   To generate the FAL API key:
   - Go to https://fal.ai/dashboard
   - Click on "Keys" in the sidebar
   - Click "Create new key" to generate a new API key
   - Copy the generated key and paste it into your `.env` file

4. Run the application:
   ```
   python app.py
   ```

5. Open your web browser and navigate to `http://localhost:5000` to use SketchMaker AI.

## Usage

1. Enter a detailed description of the image you want to generate in the text area.
2. Select the desired AI model for image generation.
3. Choose from a variety of image sizes or enter custom dimensions.
4. Select artistic style, color scheme, lighting options, subject focus, and background style as needed.
5. Adjust advanced parameters like inference steps, guidance scale, and seed if desired.
6. For Flux Lora model, provide a LoRA path and scale if using custom LoRA models.
7. Click "Enhance Image Prompt" to generate an AI-enhanced prompt.
8. Review and edit the enhanced prompt if needed.
9. Click "Generate Image" to create the image based on your specifications.
10. Once the image is generated, you can download it in your preferred format.

For a detailed tutorial on how to fine-tune your images faster using Fal AI, watch this video:
[How to Fine Tune your images faster using Fal AI](https://www.youtube.com/watch?v=rKs2o1gBw3Y)

### Fine-Tuning with Flux Lora Fast Training

To create custom LoRA models for specialized image generation:

1. Visit the [Flux Lora Fast Training model page](https://fal.ai/models/fal-ai/flux-lora-fast-training)
2. Follow the instructions to fine-tune the model with your specific dataset
3. Once fine-tuning is complete, save your model to Hugging Face or copy the safetensors URL
4. In SketchMaker AI, select the Flux Lora model and paste your custom LoRA URL in the LoRA path field
5. Use your fine-tuned model to generate images tailored to your specific style or domain

This feature allows you to create innovative and creative digital assets that are uniquely suited to your brand, products, or artistic vision.

## New Features and Changes

- Added support for multiple AI models (Flux Pro, Flux Lora, Flux Dev, Flux Realism).
- Expanded image size options to include various social media and common use case dimensions.
- Introduced subject focus and background style options for more precise image generation.
- Added effects and filters selection for image enhancement.
- Implemented advanced parameter controls (inference steps, guidance scale, seed).
- Added LoRA support for the Flux Lora model.
- Enhanced the prompt generation process with editable results.
- Improved the user interface for a more intuitive image generation workflow.

## Contributing

We welcome contributions to SketchMaker AI! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Make your changes and commit them with clear, descriptive messages.
4. Push your changes to your fork.
5. Submit a pull request with a clear description of your changes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenAI for their powerful language models
- FAL AI for their image generation capabilities
- All contributors and users of SketchMaker AI

## Contact

For any queries or support, please open an issue on the GitHub repository or contact the maintainers directly.

---

Enjoy creating amazing images with SketchMaker AI!
