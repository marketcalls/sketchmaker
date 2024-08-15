# SketchMaker AI

SketchMaker AI is an advanced AI-powered image generation tool that creates custom images based on user descriptions and preferences. It's designed to produce high-quality, tailored images for various purposes such as social media content, blog posts, and more.

## Features

- **AI-Powered Image Generation**: Generate unique images based on textual descriptions.
- **Customizable Image Sizes**: Choose from preset sizes or specify custom dimensions.
- **Artistic Style Selection**: Apply various artistic styles to your generated images.
- **Color Scheme Options**: Select from different color palettes to match your needs.
- **Lighting and Mood Control**: Adjust the lighting and overall mood of the generated images.
- **Multi-Format Downloads**: Download your images in WebP, PNG, and JPEG formats.
- **User-Friendly Interface**: Easy-to-use web interface built with modern design principles.

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

3. Set up environment variables: (rename .sample.env file to .env file)
   Create a `.env` file in the root directory and add your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   FAL_KEY=your_fal_api_key
   OPENAI_MODEL=your_preferred_openai_model
   FLUX_PRO_MODEL=your_preferred_flux_pro_model
   ```

4. Run the application:
   ```
   python app.py
   ```

5. Open your web browser and navigate to `http://localhost:5000` to use SketchMaker AI.

## Usage

1. Enter a detailed description of the image you want to generate in the text area.
2. Select the desired image size, or enter custom dimensions.
3. Choose artistic style, color scheme, and lighting options as needed.
4. Click "Enhance Image Prompt" to generate an AI-enhanced prompt.
5. Review the generated prompt and click "Approve Prompt" to create the image.
6. Once the image is generated, you can download it in your preferred format.

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
