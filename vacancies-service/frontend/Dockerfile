# Фронтенд в Compose работает только как Vite dev-server: демо-страница
# (раздел 7 ТЗ) запускается вместе с бэкендом и живёт на сид-данных.
# Multi-stage сборка под nginx сознательно не делается — продакшен-раздача
# статики в задачи этого сервиса не входит.
FROM node:24-alpine

WORKDIR /srv

# Отдельным слоём, чтобы npm ci не повторялся при каждой правке исходников.
# `npm ci` требует package-lock.json; `|| npm install` — запасной путь для
# первой сборки, когда лок-файл ещё не сгенерирован.
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
