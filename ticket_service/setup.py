# ticket_service/setup.py
import os
from setuptools import setup, find_packages


long_description = ""
long_description_content_type = "text/markdown"


this_directory = os.path.abspath(os.path.dirname(__file__))

readme_path = os.path.join(this_directory, 'README.md')

try:
    with open(readme_path, encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:

    print(f"WARNING: README.md not found at {readme_path}. Using empty long_description.")

    pass

setup(
    name='helpdesk-ticket-service',
    version='0.1.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
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
            'ticket_service_app=ticket_service.main:app',
        ],
    },
    author='Umut Celik',
    author_email='umut.celik@cloudpro.com.tr',
    description='Helpdesk Ticket Management Service',
    long_description=long_description,
    long_description_content_type=long_description_content_type,
    url='https://dev.azure.com/umutcelik0234/HelpDesk_App/_git/helpdesk-app-src',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.11',
)