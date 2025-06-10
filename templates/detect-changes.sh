# templates/detect-changes.sh

# Hata durumunda script'in durmasını sağla
set -e

echo "Değişen servisler algılanıyor..."
# Azure Pipelines'ın klonladığı reponun tam geçmişine ihtiyacımız var.
# Bu yüzden pipeline'da 'fetchDepth: 0' ayarı önemlidir.
# Son commit ile bir önceki commit arasındaki farkları alıyoruz.
CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD)

echo "Değişen dosyalar:"
echo "$CHANGED_FILES"

# Her servis için bir bayrak (flag) oluşturuyoruz. Başlangıçta hepsi 'false'.
USER_SERVICE_CHANGED=false
TICKET_SERVICE_CHANGED=false
AUTH_SERVICE_CHANGED=false
FRONTEND_CHANGED=false

# Değişen her dosya için döngü
for FILE in $CHANGED_FILES; do
  if [[ "$FILE" == user_service/* ]]; then
    echo "user_service içinde değişiklik algılandı."
    USER_SERVICE_CHANGED=true
  fi
  if [[ "$FILE" == ticket_service/* ]]; then
    echo "ticket_service içinde değişiklik algılandı."
    TICKET_SERVICE_CHANGED=true
  fi
  if [[ "$FILE" == auth_service/* ]]; then
    echo "auth_service içinde değişiklik algılandı."
    AUTH_SERVICE_CHANGED=true
  fi
  if [[ "$FILE" == frontend/* ]]; then
    echo "frontend içinde değişiklik algılandı."
    FRONTEND_CHANGED=true
  fi
done

# Sonuçları, sonraki işlerin (job) kullanabilmesi için pipeline çıkış değişkenleri olarak ayarlıyoruz.
# 'isOutput=true' bu değişkenlerin diğer işler tarafından okunabilmesini sağlar.
echo "##vso[task.setvariable variable=USER_SERVICE_CHANGED;isOutput=true]$USER_SERVICE_CHANGED"
echo "##vso[task.setvariable variable=TICKET_SERVICE_CHANGED;isOutput=true]$TICKET_SERVICE_CHANGED"
echo "##vso[task.setvariable variable=AUTH_SERVICE_CHANGED;isOutput=true]$AUTH_SERVICE_CHANGED"
echo "##vso[task.setvariable variable=FRONTEND_CHANGED;isOutput=true]$FRONTEND_CHANGED"

echo "Değişkenler ayarlandı."