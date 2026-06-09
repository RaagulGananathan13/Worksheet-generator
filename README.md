<div align="center">
  <img src="public/gb-logo.jpg" alt="GeniusBees Logo" width="150"/>
  <h1>🐝 GeniusBees Worksheet Editor</h1>
  <p><strong>A powerful, visual HTML worksheet builder and editor designed for modern educators.</strong></p>
  
  <p>
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
    <img src="https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E" alt="Vite" />
    <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS" />
    <img src="https://img.shields.io/badge/Zustand-443E38?style=for-the-badge&logo=react&logoColor=white" alt="Zustand" />
  </p>
</div>

<br />

## 🌟 Overview

The **GeniusBees Worksheet Editor** is a visual worksheet editor that lets users upload, edit, export, and save worksheets to AWS S3 through a lightweight backend.

## ✨ Key Features

- **🎨 Visual WYSIWYG Editing:** Directly click and edit text, images, and layout elements right on the canvas.
- **⚡ Real-time Property Panel:** Instantly update typography (fonts, sizes, weights), colors, and alignments with live preview.
- **🔄 Undo & Redo System:** Built-in history management means you never lose your progress or make an irreversible mistake.
- **📱 Responsive & Resizable Panel:** A sleek, light-themed interface with adjustable sidebars to fit your workflow.
- **📤 Seamless Export:** Export your finished worksheets as clean HTML or high-quality PDF files.
- **☁️ AWS S3 Save:** Save worksheets to an S3 bucket with a custom file name and folder path.
- **🔒 Secure Sandboxing:** Editing happens inside a secure iframe, isolating worksheet styles from the application UI.

## 🚀 Getting Started

Follow these steps to get the project up and running on your local machine.

### Prerequisites

Make sure you have [Node.js](https://nodejs.org/) installed on your system.

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Dilukshan285/Worksheet-generator.git
   cd Worksheet-generator
   ```

2. **Install frontend dependencies:**

   ```bash
   cd frontend
   npm install
   ```

3. **Install backend dependencies:**

   ```bash
   cd ..
   cd backend
   npm install
   ```

4. **Start the frontend development server:**

   ```bash
   cd ..
   cd frontend
   npm run dev
   ```

5. **Start the backend development server:**

   ```bash
   cd ..
   cd backend
   npm run dev
   ```

6. **Build the frontend for production:**
   ```bash
   cd ..
   cd frontend
   npm run build
   ```

## Backend Setup

The project is now split into separate `frontend/` and `backend/` folders.

- Frontend: go into `frontend/` and run `npm run dev`
- Backend: go into `backend/` and run `npm run dev`

Create a `.env` file inside `backend/` from `backend/.env.example` and set your AWS settings:

```bash
AWS_REGION=us-east-1
AWS_S3_BUCKET=your-worksheet-bucket
AWS_S3_KEY_PREFIX=worksheets
PORT=3001
```

If you prefer to connect AWS through the CLI instead of environment variables, run `aws configure` once and provide your access key, secret key, default region, and output format. The backend will then use your local AWS profile automatically through the AWS SDK.

The backend exposes `POST /api/worksheets/s3`, which accepts:

- `html` - the worksheet HTML to store
- `fileName` - the file name to use in S3
- `folderPath` - the folder prefix inside the bucket

In the editor, the export modal now includes inputs for file name and S3 folder before saving.

## Folder Layout

- `frontend/` contains the React app, Vite config, static assets, and frontend package file.
- `backend/` contains the Express API, backend package file, and AWS environment example.
- The workspace root now mainly acts as the repo parent and documentation entry point.

## 🛠️ Tech Stack

- **Framework:** [React 18](https://react.dev/) with [Vite](https://vitejs.dev/)
- **Styling:** [Tailwind CSS v3](https://tailwindcss.com/)
- **State Management:** [Zustand](https://github.com/pmndrs/zustand)
- **History Management:** [Zundo](https://github.com/charkour/zundo)
- **Backend:** [Express](https://expressjs.com/) with the AWS SDK for S3

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
