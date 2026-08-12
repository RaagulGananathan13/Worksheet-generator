const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const dir = 'c:/Users/94775/Desktop/Worksheet-generator/frontend/public/assets/illustrations';

async function convert() {
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.png'));
  for (const file of files) {
    const inputPath = path.join(dir, file);
    const outputPath = path.join(dir, file.replace('.png', '.webp'));
    console.log(`Converting ${file}...`);
    await sharp(inputPath).webp({ quality: 80 }).toFile(outputPath);
    fs.unlinkSync(inputPath);
    console.log(`Converted and removed ${file}`);
  }
}

convert().catch(console.error);
