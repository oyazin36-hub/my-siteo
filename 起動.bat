@echo off
chcp 65001 > nul
title 材料出しアプリ セットアップ

echo ================================================
echo  材料出し（zumen-pickup）セットアップ
echo ================================================
echo.

:: Node.js チェック
node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Node.js がインストールされていません。
    echo.
    echo 以下のURLからNode.jsをインストールしてください：
    echo   https://nodejs.org/ja/
    echo   （「LTS」と書かれたボタンをクリック）
    echo.
    pause
    exit /b 1
)

echo [OK] Node.js が見つかりました
node --version
echo.

:: 依存パッケージのインストール
if not exist "node_modules" (
    echo パッケージをインストール中... （初回のみ・少し時間がかかります）
    npm install
    if %errorlevel% neq 0 (
        echo [エラー] インストールに失敗しました。
        pause
        exit /b 1
    )
    echo [OK] インストール完了
) else (
    echo [OK] パッケージは既にインストール済みです
)

echo.
echo アプリを起動します...
echo.
npm start
