# Green Office CV

Alp Yücel'in 3D CV sitesi. Site karanlık, büyük bir açık ofisle açılıyor; sadece ortadaki dörtlü masa öbeği aydınlık. Ona tıklayınca kamera yaklaşıyor, dört CRT'den açık olana tıklayınca içinde AlpOS masaüstü açılıyor: About, AI Lab, Now, Experience, Projects, Terminal, Paint, Snake ve Contact.

Site: https://alpyucel.com

Yayın: Vercel üzerinde (proje adı `alpyucel`), GitHub reposu `razzleedazz/green-office`'e bağlı. `main` dalına her push otomatik yayınlanır.

Domain Porkbun'dan alındı ve yılda bir yenilenir. DNS kayıtları Porkbun panelinde: kök için `A 216.198.79.1`, `www` için `CNAME cname.vercel-dns.com`. `www.alpyucel.com` ana adrese yönlenir.

## İçeriği değiştirip yayınlama

1. `site/index.html` içinde metni değiştir (aşağıdaki "İçeriği değiştirme" bölümüne bak).
2. Yerelde bak ("Yerelde açma").
3. Kaydet ve gönder:

```bash
cd ~/Desktop/ClaudeEngine/green-office && git add -A && git commit -m "Update content" && git push
```

Vercel bir iki dakika içinde yeni sürümü yayına alır. Bir şey ters giderse Vercel panelinde Deployments altından önceki sürüme "Promote to Production" ile dönebilirsin.

Dikkat: Ev klasörün (`~`) yanlışlıkla bir git reposu. Git komutlarını hep `green-office/` klasörünün içinde çalıştır.

## Klasörler

```
green-office/
├── build.sh                  site/ klasöründen yayınlanacak dist/ klasörünü üretir (Vercel bunu çalıştırır)
├── vercel.json               Vercel ayarı: build komutu, çıktı klasörü, model dosyaları için önbellek
├── site/                     sitenin kaynağı
│   ├── index.html            sayfa: Three.js sahnesi + AlpOS (CV içeriği burada). Tam bir HTML belgesi değil; build.sh sarıyor
│   ├── og.jpg                link paylaşılınca çıkan 1200x630 önizleme görseli
│   ├── office.glb.txt        Blender'da ışığı bake edilmiş ofis (base64 kodlu GLB)
│   ├── cluster.glb.txt       ofisin geri kalanındaki boş, düşük detaylı masa öbeği (base64 kodlu GLB)
│   └── workers.glb.txt       MakeHuman çalışanları, iskelet + yazma animasyonu (base64 kodlu GLB)
└── blender/                  sahneyi üreten Python script'leri
    ├── build_office.py       ofisi kurar, Cycles ile ışığı bake eder, out/office.glb üretir
    ├── workers.py            MPFB ile 3 çalışan üretir, oturtur, animasyon ekler, workers_out/workers.glb üretir
    ├── glb2txt.py            .glb dosyasını base64 .txt'ye çevirir (artifact sunucusu .glb kabul etmiyor, güvenlik kuralı data: adreslerini engelliyor)
    ├── inspect_glb.py        bir .glb dosyasının içindeki objeleri listeler (hata ayıklama için)
    ├── out/                  son bake: office.glb + dokular (repoda yok, script'ler üretir)
    └── workers_out/          workers.glb, workers.blend, önizleme (repoda yok, script'ler üretir)
```

## Gerekenler

- Blender 4.5.9 LTS: `~/Applications/Blender.app`
- MPFB 2.0.18 eklentisi ve MakeHuman system assets (CC0). İkisi de Blender'a kurulu.

## Yeniden üretme

Sıra önemli: Ofis bake'i, çalışanları gölge kaynağı olarak `workers_out/workers.glb` dosyasından okuyor.

1. Çalışanları üret:

```bash
cd ~/Desktop/ClaudeEngine/green-office/blender && ~/Applications/Blender.app/Contents/MacOS/Blender -b -P workers.py -- "$PWD/workers_out" export
```

2. Ofisi kur ve ışığı bake et. Argümanlar sırasıyla örnekleme sayısı ve doku boyutu. M4'te yaklaşık 2,5 dakika sürüyor:

```bash
cd ~/Desktop/ClaudeEngine/green-office/blender && ~/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P build_office.py -- "$PWD/out" 256 4096
```

3. Ofisin geri kalanındaki boş masa öbeğini bake et:

```bash
cd ~/Desktop/ClaudeEngine/green-office/blender && ~/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P build_office.py -- "$PWD/out" 64 1024 empty
```

4. Siteye kopyala:

```bash
cd ~/Desktop/ClaudeEngine/green-office/blender && python3 glb2txt.py out/office.glb ../site/office.glb.txt && python3 glb2txt.py workers_out/workers.glb ../site/workers.glb.txt && python3 glb2txt.py out/cluster.glb ../site/cluster.glb.txt
```

## Yerelde açma

`site/index.html` tek başına açılmaz (çift tıklayınca modeller yüklenmez). Önce build et, sonra küçük bir sunucu başlat:

```bash
cd ~/Desktop/ClaudeEngine/green-office && sh build.sh && python3 -m http.server 8000 --directory dist
```

Sonra tarayıcıda http://localhost:8000 adresini aç. Bitince terminalde Ctrl+C ile sunucuyu durdur.

## Link önizlemesi (LinkedIn, WhatsApp kartı)

Başlık, açıklama ve görsel etiketlerini `build.sh` ekler. Metinleri değiştirmek için `build.sh` içindeki `TITLE` ve `DESC` satırlarını düzenle. Site adresi Vercel'de otomatik olarak production domain'inden alınır.

Görsel `site/og.jpg`. Değiştirirsen 1200x630 piksel olsun. LinkedIn eski kartı önbellekte tutar; yenilemek için https://www.linkedin.com/post-inspector/ adresine linki yapıştır.

## İçeriği değiştirme

CV metinlerinin hepsi `site/index.html` içinde:
- `PROJECTS` listesi: proje kartları
- `APPS` nesnesi: About, AI Lab, Now, Experience, Contact pencereleri
- Giriş ekranı: dosyanın ortasındaki `<div class="gate">` bloğu
- `CMDS` nesnesi: terminal komutları

## Lisanslar

- MakeHuman varlıkları (çalışanlar, kıyafetler, dokular): CC0
- MPFB eklentisi: GPLv3. Sadece üretim aracı, sitede kodu yok.
- Three.js: MIT, jsDelivr CDN'den yükleniyor.
