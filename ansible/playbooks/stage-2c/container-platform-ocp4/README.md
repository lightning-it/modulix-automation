## OCP4 playbook sequence

Run these from `modulix-automation/ansible`:

```bash
ansible-playbook -i hosts playbooks/stage-2c/container-platform-ocp4/prepare-ee.yml
ansible-playbook -i hosts playbooks/stage-2c/container-platform-ocp4/20-ocp-install.yml
ansible-playbook -i hosts playbooks/stage-2c/container-platform-ocp4/21-post-install.yml
```
 
