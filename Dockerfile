FROM python:3.11
ADD . /src
WORKDIR /src
RUN pip install -r requirements.txt
CMD kopf run /src/podinfo_operator/podinfo_operator.py --verbose
