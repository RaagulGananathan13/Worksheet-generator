# Backend

The backend exposes a small API that stores worksheet HTML in AWS S3.

Required environment variables:

- `AWS_REGION`
- `AWS_S3_BUCKET`
- `AWS_S3_KEY_PREFIX` optional, defaults to `worksheets`
- `PORT` optional, defaults to `3001`

Run locally:

```bash
npm run dev
```