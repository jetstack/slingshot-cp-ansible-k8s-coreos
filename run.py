#!/usr/bin/env python

import yaml
import logging
import os
import os.path
import sys
import subprocess
import time


class AnsibleConfigProvider(object):
    parameters_file_path = os.path.abspath('parameters.yaml')
    ssh_key_file_path = os.path.expanduser('~/.ssh/id_rsa')
    ssh_config_file_path = os.path.expanduser('~/.ssh/config')
    ansible_inventory_file_path = os.path.abspath('inventory/slingshot')
    ansible_vars_kubernetes_file_path = os.path.abspath(
        'group_vars/kubernetes.yaml'
    )
    my_parameters = None
    my_log = None

    def __initialize__(self):
        self.my_parameters = None
        self.my_log = None

    @property
    def parameters(self):
        if self.my_parameters is None:
            with open(self.parameters_file_path, 'r') as stream:
                self.my_parameters = yaml.load(stream)
            self.log.info(
                "read parameters from '%s'" % self.parameters_file_path
            )
        return self.my_parameters

    @property
    def log(self):
        if self.my_log is None:
            l = logging.getLogger(__name__)
            l.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            ch.setFormatter(formatter)
            l.addHandler(ch)
            self.my_log = l
        return self.my_log

    def prepare(self):
        self.configure_ssh()
        self.configure_ansible()

    def write_to_file(self, path, content):
        dir_path = os.path.dirname(path)
        if not os.path.isdir(dir_path):
            os.makedirs(dir_path)

        with open(path, 'w') as stream:
            stream.write(content)

    def configure_ssh(self):
        self.configure_ssh_key()
        self.configure_ssh_config()

    def configure_ssh_config(self):
        output = []
        for host in self.parameters['inventory']:
            if 'bastion' in host['roles']:
                output += [
                    'Host bastion',
                    '   Hostname %s' % host['publicIP'],
                    '   User core',
                    '   ForwardAgent yes',
                    '   ControlMaster auto',
                    '   ControlPath ~/.ssh/ansible-%r@%h:%p',
                    '   ControlPersist 5m',
                    '   StrictHostKeyChecking no',
                    ''
                ]

            output += [
                'Host %s' % host['name'],
                '   StrictHostKeyChecking no',
            ]
            if host['publicIP'] is None:
                output += [
                    '   ProxyCommand ssh -q bastion ncat %h 22',
                    '   Hostname %s' % host['privateIP']
                ]
            else:
                output += [
                    '   Hostname %s' % host['publicIP']
                ]
            output.append('')

        self.write_to_file(
            self.ssh_config_file_path,
            '\n'.join(output),
        )
        self.log.info(
            "successfully wrote ssh config to '%s'" % self.ssh_config_file_path
        )

    def configure_ssh_key(self):
        try:
            ssh = self.parameters['general']['authentication']['ssh']
            key = ssh['privateKey']

            if os.path.exists(self.ssh_key_file_path):
                self.log.warn(
                    "Won't overwrite the key in '%s'" % self.ssh_key_file_path
                )
                return None

            self.write_to_file(self.ssh_key_file_path, key)

            os.chmod(self.ssh_key_file_path, 0600)

            self.log.info(
                "successfully wrote ssh key to '%s'" % self.ssh_key_file_path
            )
        except Exception as e:
            self.log.warn('writing of ssh key failed: %s' % e)

    def configure_ansible(self):
        self.configure_ansible_inventory()
        self.configure_ansible_params()

    def configure_ansible_params(self):
        conf = self.parameters['general']['cluster']
        path = self.ansible_vars_kubernetes_file_path
        with open(path, 'w') as outfile:
            outfile.write(yaml.dump(conf, default_flow_style=False))
        self.log.info(
            "successfully wrote group_vars to '%s'" % path
        )

    def configure_ansible_inventory(self):
        self.write_to_file(
            self.ansible_inventory_file_path,
            self.ansible_inventory()
        )
        self.log.info(
            "successfully wrote ansible inventory to '%s'" %
            self.ansible_inventory_file_path
        )
        pass

    def ansible_inventory(self):
        content = """[kubernetes-master]
%s
[kubernetes-worker]
%s
[etcd:children]
kubernetes-master

[kubernetes:children]
kubernetes-master
kubernetes-worker

[coreos:children]
kubernetes
""" % (
            self.ansible_hosts('master'),
            self.ansible_hosts('worker'),
        )
        return content

    def ansible_hosts(self, role):
        output = ''
        for host in self.parameters['inventory']:
            if role in host['roles']:
                ips = ' '.join([
                    '%s=%s' % (ip, host[ip])
                    for ip in ['privateIP', 'publicIP']
                    if host[ip] is not None
                ])
                output += "%s %s\n" % (host['name'], ips)

        return output

    def run_command(self, cmd):
        p = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        p.communicate()
        return p

    def apply(self):
        self.prepare()

        tries = 0
        while True:
            self.log.info("check connectivity to all nodes:")
            p = self.run_command(
                ["ansible", "-m", "raw", "-a", "uptime", "coreos"],
            )
            if p.returncode == 0:
                break
            tries += 1
            if tries >= 10:
                sys.exit(1)
            wait_time = 0.1*(2**tries)
            self.log.warn(
                "connectivity check failed, -> retrying in %f seconds" %
                wait_time
            )
            time.sleep(wait_time)

        p = self.run_command(
            ["ansible-playbook", "cluster.yaml", "-l", "coreos"],
        )
        sys.exit(p.returncode)

    def discover(self):
        print("""provider:
  type: config
  version: 1
commands:
  apply:
    execs:
      -
        - apply
    type: docker
    parameterFile: %s
    persistPaths:
    - ssl_ca/""" % os.path.basename(self.parameters_file_path))

    def command(self, argv):
        cmd = argv[1]
        if cmd == 'discover':
            return self.discover()
        elif cmd == 'apply':
            return self.apply()
        else:
            print("Unknown command '%s'" % cmd)
            sys.exit(1)


def main():
    acp = AnsibleConfigProvider()
    acp.command(sys.argv)


if __name__ == "__main__":
    main()
