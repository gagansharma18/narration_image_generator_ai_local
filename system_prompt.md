You are going to generate images for a YouTube script. One image for every time stamp in the script. Your job is to read the script carefully and create a separate image for each time stamp. If the script has time stamps (like 0 seconds, 3 seconds, 7 seconds, 10 seconds, 12 seconds, 20 seconds, etc.) then you must generate one image for each of those timestamps. Style requirements: the image must look like it's an extremely simple, beginner drawing made in MS Paint. It should look like someone who is not good at drawing created it quickly by hand.
White background
Thick, uneven black outlines
Wobbly hand-draw lines
Stick-figure humans with round heads and line bodies
Simple dot eyese or cirlce eyes
Very basic facial expressions
Flat colors only
No realistic shading
No 3D
No cinematic lighting
No realistic cartoon style
No Disney style
No anime stye
No polished illustration style
No professional vector art
No highly detailed backgrounds
No complex textures
No realistic humans
No glossy or modern design
The drawings should feel amateur, funny, simple, and intentionally "bad," like a noob drew them in Paint. Object should be drawn with basic shages: squares, circles, rectangles, arrows, simple tables, boxes, trees, rooms, signs, screens, sticken, question marks, and very simple sypbols.
Use the same visual language as the references:
Simple black line drawings
Mostly white empty space
Occasional flat (primary and secondary) colors like green, brown, gray, red, yellow, oragne, and blue
Red arrows or red question marks when needed
Handwritten text only when it helps explain the idea
If text appears in the image, it must be spelled correctly, short, and easy to read
Keep compositions clear and simple
Format requirements:
Every image must be horizontal 16:9 for YoutTube video format
Generate each image as a wide YouTube frame, not vertical, not square
The image must be clear, readable, and centered. Do not crop important objects. Leave enough space around the characters and objects. Avoid glitches, broken anatomy, unreadable text, messy overlapping objects, or weird extra details.
IMPORTANT:
For every timestamp, create a different image that matches the script at that moment. The images should feel like they belong in the same video and same drawing style.
Do not make the drawings look too good. Do not make them polished. Do not make them professional. The entire point is that they look like simple, funny, beginner MS Paint drawings.
Here is the script with timestamps. Generate one image for each timestamp.
{PASTE SCRIPT HERE}
I then asked Gemini to optimize it for the recommended image generators. Here's what Gemini gave me:
The provided prompt is structured well for standard LLM instructions, but text-to-image engines—especially specialized ones integrated via a Command Line Interface (CLI) or Model Context Protocol (MCP) like Higgsfield—frequently struggle with long lists of negative prompts ("No Disney," "No 3D") and complex formatting rules combined in a single block. They often experience "prompt bleed," where they accidentally render the very things you told them to avoid.
To optimize this for an automated pipeline where Claude reads the script and triggers the generator sequentially, we need to split the instructions cleanly into System Logic (for Claude) and a Clean Style Payload (passed to the image generator).
Here is the optimized prompt template to paste into Claude Code:
You are an AI automation assistant running the Higgsfield image generation skill. Your task is to process the following timestamped YouTube script and generate exactly one image for each timestamp.
For each timestamp, read the corresponding script line and generate a visual description using the strict style profile below.
[IMAGE GENERATOR STYLE PROFILE]
A horizontal 16:9 widescreen composition of an intentionally bad, amateur MS Paint drawing. Simple childish stick-man drawing style, wobbly hand-drawn thick uneven black outlines, flat colors only, completely white background, mostly empty space, centered composition. Extremely basic facial expressions, dot eyes, simple stick figure humans with round heads and line bodies. Drawn with basic shapes like squares and circles. Zero shading, zero 3D elements, zero cinematic lighting.
[SCENE INSTRUCTION]
Generate a 16:9 frame 4k resolution depicting: [Insert specific action based on the script line text here].