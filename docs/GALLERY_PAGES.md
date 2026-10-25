# GitHub Pages 图库

用户已授权：主项目保持私有，图库网页及加工卡片允许公开访问。

- 私有主项目：https://github.com/dajiangde/mcd-hidden-explorer
- 独立公开图库仓库：https://github.com/dajiangde/mc-master-eater-gallery
- Pages 地址：https://dajiangde.github.io/mc-master-eater-gallery/
- 发布分支：`codex/gallery-pages`，根目录 `/`，包含 `.nojekyll`。

私有主项目的 Pages 创建请求在2026-10-25返回422：`Your current plan does not support GitHub Pages for this repository.` 因此将已授权公开的网页资产放在独立公开仓库；未将主项目改为公开，没有升级套餐。公开图库采用独立根提交，不包含私有主项目历史。

## 文件边界

发布目录只有46个文件：`index.html`、`.nojekyll`、22个`cards/U*.png`、22个`thumbnails/U*.png`。固定编号U12停用保留，不重新分配；配方说明与来源页面链接保留。

不发布原图、原图CDN地址、签名参数、研究catalog、数据库、ZIP、历史缓存、渲染模板或Skill源码。页面去掉了原始资料图库入口及批量数据下载，单卡下载明确标注“下载卡片”。所有公开图片都可以被访问和复制，私有主项目不为公开图库提供访问控制。

## 从本地资料重建

在主项目根目录运行（输出目录必须不存在）：

```sh
python3 scripts/build_gallery_site.py \
  --cards work/assets/hidden-menu-photos-20261024/base-cards-v1 \
  --output /tmp/mcd-gallery-site-new \
  --report /tmp/mcd-gallery-site-new-report.json

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_gallery_site.py -v
```

构建器核对活动编号、加工PNG哈希、图片路径和HTML依赖；仅按白名单复制卡片与缩图。移除维护入口和整包/数据下载链接，清除来源链接的查询与签名参数。原始图库和原始图片不改动。

## 后续更新

重新导出后，在独立图库仓库的临时检出中更新这46类白名单文件，并先检查待提交文件与新报告一致。只将网页产物推送到图库仓库的`codex/gallery-pages`分支，不将主项目根目录或研究目录推送过去；不使用强制推送或混入主项目历史。该分支更新会触发Pages构建。

发布后分别核验：Pages构建成功、匿名HTTP访问、图片字节/哈希、浏览器真实出图、编号搜索、餐品搜索、分类及来源展开。HTTPS图址在WorkBuddy正文的效果尚需独立实测；本次未修改Skill安装包或图片交付规则。

本轮证据：`work/validation/github-pages-gallery-20261025/`；冻结网页：`work/local-bundles/gallery-pages-20261025/site/`。
