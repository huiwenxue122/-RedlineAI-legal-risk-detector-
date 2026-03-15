# 前端部署：让别人打开就能用

后端已在 Render 运行（例如 `https://contractsentinel.onrender.com`）。把前端也部署到公网后，别人打开前端地址即可使用整个产品。

---

## 方式一：Vercel 部署（推荐，Next.js 零配置）

1. **把代码推到 GitHub**（若尚未推送）
   ```bash
   git add . && git commit -m "Add frontend" && git push
   ```

2. **登录 [Vercel](https://vercel.com)**，用 GitHub 登录。

3. **Import 你的仓库**
   - 选 ContractSentinel 仓库
   - **Root Directory** 填：`frontend`
   - **Framework Preset** 选 Next.js（一般会自动识别）
   - **Build Command**：`npm run build`（默认即可）
   - **Output Directory**：默认

4. **环境变量**
   - 在导入时或 Project → Settings → Environment Variables 里添加：
   - **Name**: `NEXT_PUBLIC_API_URL`
   - **Value**: `https://contractsentinel.onrender.com`（换成你真实的 Render 后端地址）
   - 不要加末尾斜杠

5. **Deploy**。完成后会得到一个地址，例如 `https://contractsentinel-xxx.vercel.app`。

6. **分享**：把这个链接发给别人，打开即可使用（前端会请求你的 Render 后端）。

---

## 方式二：Render 上再开一个前端服务

1. 在 [Render Dashboard](https://dashboard.render.com) 点 **New → Web Service**。

2. 连接同一个 GitHub 仓库。

3. 配置：
   - **Name**: 例如 `contractsentinel-frontend`
   - **Root Directory**: `frontend`
   - **Runtime**: Node
   - **Build Command**: `npm install && npm run build`
   - **Start Command**: `npm start`
   - **Instance Type**: Free

4. **Environment** 添加：
   - `NEXT_PUBLIC_API_URL` = `https://contractsentinel.onrender.com`（你的后端地址）

5. 创建并等待部署。会得到类似 `https://contractsentinel-frontend.onrender.com` 的地址。

---

## 部署后检查

- 打开前端链接，点「Demo 合同」或上传合同，能跑通即表示前后端都正常。
- 若请求失败：确认前端环境变量里的 `NEXT_PUBLIC_API_URL` 与后端地址一致，且后端 CORS 允许该前端域名（当前后端为 `*`，一般没问题）。

---

## 本地开发时

- 前端根目录可建 `.env.local`：
  ```bash
  NEXT_PUBLIC_API_URL=http://localhost:8000
  ```
- 不填则默认连 `http://localhost:8000`（见 `frontend/lib/api.ts`）。
