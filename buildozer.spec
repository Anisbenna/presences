[app]

title = Presences
package.name = presences
package.domain = org.presences

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas

version = 1.0
requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0

android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

android.api = 31
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

android.allow_backup = True

p4a.branch = master
