FROM debian:jessie
MAINTAINER Christian Simon <simon@swine.de>

RUN apt-get update &&  \
    DEBIAN_FRONTEND=noninteractive apt-get -y install curl build-essential \
    python-pip libffi-dev libgmp-dev python-dev libyaml-dev nano libssl-dev \
    openssh-client && \
    apt-get clean && \
    rm /var/lib/apt/lists/*_*


# get cfssl
ENV CFSSL_VERSION 1.2
ENV CFSSL_HASH eb34ab2179e0b67c29fd55f52422a94fe751527b06a403a79325fed7cf0145bd
ENV CFSSLJSON_HASH 1c9e628c3b86c3f2f8af56415d474c9ed4c8f9246630bd21c3418dbe5bf6401e
RUN curl -s -L -o /usr/local/bin/cfssl     https://pkg.cfssl.org/R${CFSSL_VERSION}/cfssl_linux-amd64 && \
    curl -s -L -o /usr/local/bin/cfssljson https://pkg.cfssl.org/R${CFSSL_VERSION}/cfssljson_linux-amd64 && \
    chmod +x /usr/local/bin/cfssl /usr/local/bin/cfssljson && \
    echo "${CFSSL_HASH}  /usr/local/bin/cfssl" | sha256sum -c && \
    echo "${CFSSLJSON_HASH}  /usr/local/bin/cfssljson" | sha256sum -c

RUN groupadd -g 950 ansible && \
    useradd -u 950 -g 950 -d /ansible ansible

WORKDIR /ansible/code
COPY requirements.txt /ansible/code/
RUN pip install -r requirements.txt
RUN chown -cR ansible:ansible /ansible
RUN chown -cR ansible:ansible /ansible

USER ansible


COPY ansible.cfg /ansible/code/
COPY requirements.yaml /ansible/code/
RUN ansible-galaxy -r requirements.yaml install

COPY cluster.yaml /ansible/code/
COPY group_vars/coreos.yaml /ansible/code/group_vars/
COPY group_vars/all.yaml /ansible/code/group_vars/kubernetes.yaml
COPY roles /ansible/code/
COPY run.py /ansible/run.py

# TODO: remove me only for dev
COPY parameters.yaml /ansible/code/

USER root
RUN chown -cR ansible:ansible /ansible
USER ansible

ENTRYPOINT ["/usr/bin/python", "/ansible/run.py"]

CMD discover
