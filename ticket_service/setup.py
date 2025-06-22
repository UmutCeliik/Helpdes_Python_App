# ticket_service/setup.py
from setuptools import setup, find_packages

setup(
    name='helpdesk-ticket-service',
    version='0.1.0', # Bu versiyonu pipeline'daki Build.BuildId ile dinamik hale getirebiliriz
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        # requirements.txt dosyasındaki bağımlılıkları buraya kopyala
        # Veya setup.py'nin requirements.txt'yi okumasını sağlayabiliriz.
        # Basitlik için şimdilik manuel kopyalayalım veya en önemlilerini ekleyelim.
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
    long_description=open('README.md').read(), # Eğer README.md varsa
    long_description_content_type='text/markdown',
    url='https://dev.azure.com/umutcelik0234/HelpDesk_App/_git/helpdesk-app-src', # Proje URL'i
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License', # Lisansını buraya ekle
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.11',
)