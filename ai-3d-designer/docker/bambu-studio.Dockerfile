# Bambu Studio CLI を動かすためのコンテナ。
#
# 印刷時間とフィラメント使用量を実測するために使う。
# これが無くてもアプリは動く(体積からの概算にフォールバックする)。
#
# 使い方:
#   docker build -f docker/bambu-studio.Dockerfile -t bambu-cli .
#   docker run --rm -v "$PWD/var:/data" bambu-cli --slice 0 /data/model.3mf
#
# 注意:
#   Bambu Studio は AppImage で配布されており、CLI モードでも GUI ライブラリを
#   要求する。そのため見た目より依存が多い。バージョンは実際に使う版に合わせて
#   BAMBU_VERSION を変更すること。
#   このイメージは検証環境では未検証(Docker デーモンが使えなかったため)。
#   初回は手元でビルドして動作を確認してから本番へ入れること。

FROM ubuntu:24.04

ARG BAMBU_VERSION=v01.10.02.76
ARG BAMBU_ASSET=Bambu_Studio_ubuntu-24.04_PR-7106.AppImage

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        # AppImage の展開に必要
        file zlib1g \
        # Bambu Studio が要求する GUI 系ライブラリ(CLI モードでもリンクされる)
        libgtk-3-0 libwebkit2gtk-4.1-0 libgl1 libegl1 libglu1-mesa \
        libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
        libsoup-3.0-0 libsecret-1-0 \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/bambu

RUN curl -fsSL -o bambu.AppImage \
        "https://github.com/bambulab/BambuStudio/releases/download/${BAMBU_VERSION}/${BAMBU_ASSET}" \
    && chmod +x bambu.AppImage \
    # AppImage は FUSE を必要とするが、コンテナ内では使えないので展開して使う
    && ./bambu.AppImage --appimage-extract > /dev/null \
    && rm bambu.AppImage \
    && ln -s /opt/bambu/squashfs-root/AppRun /usr/local/bin/bambu-studio

# CLI モードでも X11 のディスプレイを開こうとするため、仮想ディスプレイを噛ませる
ENV DISPLAY=:99
COPY docker/bambu-entrypoint.sh /usr/local/bin/bambu-entrypoint
RUN chmod +x /usr/local/bin/bambu-entrypoint

ENTRYPOINT ["/usr/local/bin/bambu-entrypoint"]
