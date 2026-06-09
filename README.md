<div align="center">
  <img src="frontend/public/gb-logo.jpg" alt="GeniusBees Logo" width="150"/>
  <h1>🐝 GeniusBees Worksheet Editor</h1>
  <p><strong>A powerful, visual HTML worksheet builder and editor designed for modern educators.</strong></p>
  
  <p>
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
    <img src="https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E" alt="Vite" />
    <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS" />
    <img src="https://img.shields.io/badge/Express-000000?style=for-the-badge&logo=express&logoColor=white" alt="Express" />
    <img src="https://img.shields.io/badge/AWS_S3-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white" alt="AWS" />
  </p>
</div>

<br />

## 🌟 Overview

The **GeniusBees Worksheet Editor** is a visual worksheet editor that lets users upload, edit, export, and save worksheets to AWS S3. The project is split into a React frontend and an Express backend.

## ✨ Key Features

- **🎨 Visual WYSIWYG Editing:** Directly click and edit text, images, and layout elements right on the canvas.
- **⚡ Real-time Property Panel:** Instantly update typography (fonts, sizes, weights), colors, and alignments with live preview.
- **🔄 Undo & Redo System:** Built-in history management means you never lose your progress or make an irreversible mistake.
- **📱 Responsive & Resizable Panel:** A sleek, light-themed interface with adjustable sidebars to fit your workflow.
- **📤 Seamless Export:** Export your finished worksheets as clean HTML or high-quality PDF files.
- **☁️ AWS S3 Save:** Save worksheets directly to an S3 bucket with a custom file name and folder path.
- **🔒 Secure Sandboxing:** Editing happens inside a secure iframe, isolating worksheet styles from the application UI.

## 📂 Project Structure

The application uses a separated frontend and backend structure:

- `frontend/`: Continues the React application, Vite configuration, and all UI components.
- `backend/`: Continues the Node.js/Express server that acts as a proxy to securely upload the generated HTML to an AWS S3 Bucket.

## 🚀 Getting Started

### Prerequisites

Make sure you have [Node.js](https://nodejs.org/) installed on your system.

### 1. Setup the Backend

1. **Navigate to the backend folder a install dependencies:**

   ```bash
   cd backend
   npm install
   ```

2. **Configure Environment Variables:**
   Copy the `.env.example` to `.env` and fill in your AWS details.

   ```bash
   cp .env.example .env
   ```

   Inside `backend/.env`:

   ```env
   AWS_REGION=us-east-1
   AWS_S3_BUCKET=geniusbees-worksheet-generator
   AWS_S3_KEY_PREFIX=worksheets
   PORT=3001

   # Put your IAM user keys here (ensure no quotes are around the values)
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=xxx...
   ```

3. **Start the API server:**
   ```bash
   npm run dev
   ```
   _The backend will run on `http://localhost:3001`._

### 2. Setup the Frontend

1. **Open a new terminal, navigate to the frontend folder and install dependencies:**

   ```bash
   cd frontend
   npm install
   ```

2. **Start the frontend app:**
   ```bash
   npm run dev
   ```
   _The frontend will run on `http://localhost:5173` and proxy API calls to the backend automatically._

## 🛠️ Tech Stack

- **Frontend:** [React 18](https://react.dev/), [Vite](https://vitejs.dev/), [Tailwind CSS](https://tailwindcss.com/), [Zustand](https://github.com/pmndrs/zustand)
- **Backend:** [Express](https://expressjs.com/), [AWS SDK for Node.js](https://aws.amazon.com/sdk-for-javascript/)

## 🎨 Theme & Design

The application follows the official **GeniusBees** brand identity:

- **Primary:** Orange (`#F57C00`)
- **Secondary:** Green (`#4CAF50`) & Purple (`#7B1FA2`)
- **Background:** Clean White (`#FFFFFF`) with subtle surface layers.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/Dilukshan285/Worksheet-generator/issues).

---

<div align="center">
  <i>Built with ❤️ by GeniusBees</i>
</div>
