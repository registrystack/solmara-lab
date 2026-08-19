FROM node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app
RUN corepack enable

COPY home/package.json home/pnpm-lock.yaml home/pnpm-workspace.yaml ./home/
WORKDIR /app/home
ENV CI=true
RUN pnpm install --frozen-lockfile

COPY home ./
COPY portal/src/lib/design/tokens.css /app/portal/src/lib/design/tokens.css
COPY docs /app/docs
COPY geo /app/geo
COPY generator/output /app/generator/output
COPY output/smoke /app/output/smoke
COPY metadata/public /app/metadata/public
COPY compose.yaml versions.env /app/

ENV SOLMARA_LAB_ROOT=/app
ENV CI=true
RUN pnpm build

FROM node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32

WORKDIR /app/home
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=4301
ENV SOLMARA_LAB_ROOT=/app

COPY --from=build /app/home/build ./build
COPY --from=build /app/home/node_modules ./node_modules
COPY --from=build /app/home/package.json ./package.json
COPY --from=build /app/docs /app/docs
COPY --from=build /app/geo /app/geo
COPY --from=build /app/generator/output /app/generator/output
COPY --from=build /app/output/smoke /app/output/smoke
COPY --from=build /app/metadata/public /app/metadata/public
COPY --from=build /app/compose.yaml /app/compose.yaml
COPY --from=build /app/versions.env /app/versions.env

EXPOSE 4301
CMD ["node", "build"]
