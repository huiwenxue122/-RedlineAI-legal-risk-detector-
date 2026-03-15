# ContractSentinel 前端

Next.js 14 (App Router) + TypeScript + Tailwind。证据导向审查布局：左侧合同/条款展示，右侧风险卡片列表。

## 运行

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 [http://localhost:3000](http://localhost:3000)。需先启动后端 API（`uvicorn app.main:app --reload`）。可选环境变量：`NEXT_PUBLIC_API_URL=http://localhost:8000`（默认即此）。
