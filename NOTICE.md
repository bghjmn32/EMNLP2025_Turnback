# Third-Party Notice

## English

- The code in this release is licensed under the MIT license in [LICENSE](LICENSE).
- The `36kroutes/` directory is released as the raw route collection used in the project. Route geometries and street-network structure ultimately depend on OpenStreetMap data. Please keep the attribution to OpenStreetMap contributors when redistributing or adapting the data.
- The route-generation pipeline relies on OpenRouteService at generation time. Public API access is not bundled in this repository; users must provide their own key and comply with the provider's terms.
- The reverse-instruction pipeline supports external LLM providers such as OpenAI and Gemini. API keys are never stored in this repository.

## 中文

- 本次发布中的代码采用 [LICENSE](LICENSE) 中的 MIT 许可证。
- `36kroutes/` 目录按原始路线集合发布。路线几何与街道网络结构最终依赖于 OpenStreetMap 数据；在再分发或改编数据时，请保留对 OpenStreetMap contributors 的署名。
- 路线生成流程在生成阶段依赖 OpenRouteService。仓库不附带公共 API 访问权限，使用者需自行提供密钥并遵守服务条款。
- 反转指令生成流程支持 OpenAI、Gemini 等外部大模型接口。API 密钥不会存储在本仓库中。
