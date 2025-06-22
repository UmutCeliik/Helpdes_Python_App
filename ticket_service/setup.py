# ticket_service/setup.py
import os # 'os' modülünü import ediyoruz, dosya yollarını yönetmek için
from setuptools import setup, find_packages

# long_description'ı varsayılan olarak boş bir string olarak başlatın
long_description = ""
long_description_content_type = "text/markdown" # Varsayılan olarak markdown içeriği

# setup.py dosyasının bulunduğu dizini alın
this_directory = os.path.abspath(os.path.dirname(__file__))
# README.md dosyasının tam yolunu oluşturun
readme_path = os.path.join(this_directory, 'README.md')

# README.md dosyasını okumaya çalışın
# Eğer dosya yoksa, FileNotFoundError hatası yakalanacak ve long_description boş kalacak
try:
    with open(readme_path, encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    # Dosya bulunamadığında bir uyarı mesajı yazdırın
    print(f"WARNING: README.md not found at {readme_path}. Using empty long_description.")
    # long_description varsayılan olarak boş kalacaktır
    pass # Hata durumunda script'in durmamasını sağlar

setup(
    name='helpdesk-ticket-service',
    version='0.1.0', # Bu versiyonu pipeline'daki Build.BuildId ile dinamik hale getirebiliriz
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        # requirements.txt dosyasındaki bağımlılıkları buraya kopyala
        'fastapi==0.111.0',
        'uvicorn[standard]==0.29.0',
        'SQLAlchemy==2.0.30',
        'psycopg2-binary==2.9.9',
        'alembic==1.13.1',
        'python-jose[cryptography]==3.3.0',
        'pyjwt==2.8.0',
        'httpx==0.27.0',
        'python-dotenv==1.0.1',
        'pydantic==2.7.1',
        'pydantic-settings==2.2.1',
        'hvac==1.2.0',
    ],
    entry_points={
        'console_scripts': [
            'ticket_service_app=ticket_service.main:app', # Uygulamanın ana giriş noktası
        ],
    },
    author='Umut Celik',
    author_email='umut.celik@cloudpro.com.tr',
    description='Helpdesk Ticket Management Service',
    long_description=long_description, # Güncellenen long_description değişkenini kullanın
    long_description_content_type=long_description_content_type, # İçerik tipini de kullanın
    url='https://dev.azure.com/umutcelik0234/HelpDesk_App/_git/helpdesk-app-src', # Proje URL'i
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License', # Lisansını buraya ekle
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.11',
)