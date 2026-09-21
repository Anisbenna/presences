name: Build APK

on:
  workflow_dispatch:
  push:
    branches: [ main, principal ]

jobs:
  build:
    runs-on: ubuntu-22.04

    steps:
    - name: Checkout
      uses: actions/checkout@v4

    - name: Setup Python 3.11
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Installer les dépendances système
      run: |
        sudo apt-get update
        sudo apt-get install -y \
          git zip unzip openjdk-17-jdk autoconf automake libtool \
          pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
          cmake libffi-dev libssl-dev build-essential ccache

    - name: Installer Buildozer et Cython
      run: |
        pip install --upgrade pip setuptools wheel
        pip install buildozer cython==0.29.36

    - name: Compiler l'APK
      run: |
        yes | buildozer -v android debug

    - name: Uploader l'APK
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: apk-package
        path: bin/*.apk
        if-no-files-found: warn
