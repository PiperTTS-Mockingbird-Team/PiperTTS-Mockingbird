"""
Simple SVG to ICO converter for the Mockingbird icon.
Creates a Windows-compatible .ico file from the SVG.
Uses Inkscape or ImageMagick if available, otherwise renders a simple bird icon.
"""
from pathlib import Path
import subprocess
import sys

def create_simple_ico():
    """Create a mockingbird ICO file inspired by mockingbird1.svg using PIL."""
    from PIL import Image, ImageDraw
    
    script_dir = Path(__file__).resolve().parent
    ico_path = script_dir.parent / "assets" / "mockingbird.ico"
    
    # Create a 256x256 image with transparency
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Mockingbird silhouette (black like in mockingbird1.svg)
    # Body (main oval)
    draw.ellipse([70, 95, 185, 175], fill='#000000')
    
    # Head (circle)
    draw.ellipse([140, 60, 200, 120], fill='#000000')
    
    # Wing (curved shape)
    draw.ellipse([35, 85, 130, 155], fill='#000000')
    
    # Beak (small triangle pointing right)
    draw.polygon([(200, 90), (230, 88), (205, 85)], fill='#000000')
    
    # Eye (small white dot)
    draw.ellipse([172, 85, 182, 95], fill='white')
    
    # Tail feathers (elongated shapes)
    draw.ellipse([25, 120, 80, 160], fill='#000000')
    draw.polygon([(50, 135), (20, 155), (45, 145)], fill='#000000')
    draw.polygon([(55, 145), (15, 175), (50, 155)], fill='#000000')
    
    # Legs (thin lines)
    draw.line([(110, 175), (110, 205)], fill='#000000', width=3)
    draw.line([(145, 175), (145, 205)], fill='#000000', width=3)
    
    # Feet (small lines at bottom)
    draw.line([(110, 205), (100, 215)], fill='#000000', width=2)
    draw.line([(110, 205), (120, 215)], fill='#000000', width=2)
    draw.line([(145, 205), (135, 215)], fill='#000000', width=2)
    draw.line([(145, 205), (155, 215)], fill='#000000', width=2)
    
    # Save as ICO with multiple sizes
    img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    return ico_path

def svg_to_ico_inkscape():
    """Try to convert SVG to PNG using Inkscape, then to ICO."""
    script_dir = Path(__file__).resolve().parent
    svg_path = script_dir.parent / "assets" / "mockingbird1.svg"
    png_path = script_dir.parent / "assets" / "mockingbird_temp.png"
    ico_path = script_dir.parent / "assets" / "mockingbird.ico"
    
    # Try Inkscape first
    inkscape_paths = [
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
        "inkscape"
    ]
    
    for inkscape in inkscape_paths:
        try:
            subprocess.run([
                inkscape, str(svg_path),
                "--export-type=png",
                "--export-filename=" + str(png_path),
                "--export-width=256",
                "--export-height=256"
            ], check=True, capture_output=True, timeout=10)
            
            # Convert PNG to ICO
            from PIL import Image
            img = Image.open(png_path)
            img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
            png_path.unlink()  # Clean up temp file
            return ico_path
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    
    return None

def svg_to_ico():
    """Convert mockingbird SVG to ICO."""
    script_dir = Path(__file__).resolve().parent
    svg_path = script_dir.parent / "assets" / "mockingbird1.svg"
    ico_path = script_dir.parent / "assets" / "mockingbird.ico"
    
    if ico_path.exists():
        print(f"Icon already exists: {ico_path}")
        return ico_path
    
    # Try using cairosvg first
    try:
        from PIL import Image
        import cairosvg
        from io import BytesIO
        
        # Convert SVG to PNG at high resolution
        png_data = cairosvg.svg2png(url=str(svg_path), output_width=256, output_height=256)
        
        # Convert PNG to ICO with multiple sizes
        img = Image.open(BytesIO(png_data))
        img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        
        print(f"Icon created using cairosvg: {ico_path}")
        return ico_path
    except ImportError:
        print("cairosvg not available, falling back to PIL")
        pass
    except Exception as e:
        print(f"cairosvg failed: {e}, falling back to PIL")
        pass
    
    # Try Inkscape conversion
    result = svg_to_ico_inkscape()
    if result:
        print(f"Icon created using Inkscape: {result}")
        return result
    
    # Fall back to creating a simple icon with PIL
    try:
        result = create_simple_ico()
        print(f"Icon created using PIL: {result}")
        return result
    except Exception as e:
        print(f"Failed to create icon: {e}")
        return None

if __name__ == "__main__":
    result = svg_to_ico()
    if result:
        print(f"\n✓ Success! Icon saved to: {result}")
    else:
        print("\n✗ Failed to create icon")
