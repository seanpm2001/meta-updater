# pylint: disable=C0111,C0325
import os
import logging
import re
import unittest
from time import sleep

from oeqa.selftest.case import OESelftestTestCase
from oeqa.utils.commands import runCmd, bitbake, get_bb_var, get_bb_vars
from testutils import qemu_launch, qemu_send_command, qemu_terminate, \
    akt_native_run, verifyNotProvisioned, verifyProvisioned


class GeneralTests(OESelftestTestCase):
    def test_credentials(self):
        logger = logging.getLogger("selftest")
        logger.info('Running bitbake to build core-image-minimal')
        self.append_config('SOTA_CLIENT_PROV = "aktualizr-auto-prov"')
        bitbake('core-image-minimal')
        credentials = get_bb_var('SOTA_PACKED_CREDENTIALS')
        # skip the test if the variable SOTA_PACKED_CREDENTIALS is not set
        if credentials is None:
            raise unittest.SkipTest("Variable 'SOTA_PACKED_CREDENTIALS' not set.")
        # Check if the file exists
        self.assertTrue(os.path.isfile(credentials), "File %s does not exist" % credentials)
        deploydir = get_bb_var('DEPLOY_DIR_IMAGE')
        imagename = get_bb_var('IMAGE_LINK_NAME', 'core-image-minimal')
        # Check if the credentials are included in the output image
        result = runCmd('tar -jtvf %s/%s.tar.bz2 | grep sota_provisioning_credentials.zip' %
                        (deploydir, imagename), ignore_status=True)
        self.assertEqual(result.status, 0, "Status not equal to 0. output: %s" % result.output)


class AktualizrToolsTests(OESelftestTestCase):

    @classmethod
    def setUpClass(cls):
        super(AktualizrToolsTests, cls).setUpClass()
        logger = logging.getLogger("selftest")
        logger.info('Running bitbake to build aktualizr-native tools')
        bitbake('aktualizr-native')

    def test_cert_provider_help(self):
        akt_native_run(self, 'aktualizr-cert-provider --help')

    def test_cert_provider_local_output(self):
        logger = logging.getLogger("selftest")
        logger.info('Running bitbake to build aktualizr-ca-implicit-prov')
        bitbake('aktualizr-ca-implicit-prov')
        bb_vars = get_bb_vars(['SOTA_PACKED_CREDENTIALS', 'T'], 'aktualizr-native')
        creds = bb_vars['SOTA_PACKED_CREDENTIALS']
        temp_dir = bb_vars['T']
        bb_vars_prov = get_bb_vars(['STAGING_DIR_HOST', 'libdir'], 'aktualizr-ca-implicit-prov')
        config = bb_vars_prov['STAGING_DIR_HOST'] + bb_vars_prov['libdir'] + '/sota/sota_implicit_prov_ca.toml'

        akt_native_run(self, 'aktualizr-cert-provider -c {creds} -r -l {temp} -g {config}'
                       .format(creds=creds, temp=temp_dir, config=config))

        # Might be nice if these names weren't hardcoded.
        cert_path = temp_dir + '/var/sota/import/client.pem'
        self.assertTrue(os.path.isfile(cert_path), "Client certificate not found at %s." % cert_path)
        self.assertTrue(os.path.getsize(cert_path) > 0, "Client certificate at %s is empty." % cert_path)
        pkey_path = temp_dir + '/var/sota/import/pkey.pem'
        self.assertTrue(os.path.isfile(pkey_path), "Private key not found at %s." % pkey_path)
        self.assertTrue(os.path.getsize(pkey_path) > 0, "Private key at %s is empty." % pkey_path)
        ca_path = temp_dir + '/var/sota/import/root.crt'
        self.assertTrue(os.path.isfile(ca_path), "Client certificate not found at %s." % ca_path)
        self.assertTrue(os.path.getsize(ca_path) > 0, "Client certificate at %s is empty." % ca_path)


class AutoProvTests(OESelftestTestCase):

    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of luck.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = " aktualizr-auto-prov "')
        self.qemu, self.s = qemu_launch(machine='qemux86-64')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_provisioning(self):
        print('Checking machine name (hostname) of device:')
        stdout, stderr, retcode = self.qemu_command('hostname')
        self.assertEqual(retcode, 0, "Unable to check hostname. " +
                         "Is an ssh daemon (such as dropbear or openssh) installed on the device?")
        machine = get_bb_var('MACHINE', 'core-image-minimal')
        self.assertEqual(stderr, b'', 'Error: ' + stderr.decode())
        # Strip off line ending.
        value = stdout.decode()[:-1]
        self.assertEqual(value, machine,
                         'MACHINE does not match hostname: ' + machine + ', ' + value)

        verifyProvisioned(self, machine)


class ManualControlTests(OESelftestTestCase):

    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of like.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = " aktualizr-auto-prov "')
        self.append_config('SYSTEMD_AUTO_ENABLE_aktualizr = "disable"')
        self.qemu, self.s = qemu_launch(machine='qemux86-64')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_manual_run_mode_once(self):
        """
        Disable the systemd service then run aktualizr manually
        """
        sleep(20)
        stdout, stderr, retcode = self.qemu_command('aktualizr-info')
        self.assertIn(b'Can\'t open database', stderr,
                      'Aktualizr should not have run yet' + stderr.decode() + stdout.decode())

        stdout, stderr, retcode = self.qemu_command('aktualizr once')

        stdout, stderr, retcode = self.qemu_command('aktualizr-info')
        self.assertIn(b'Fetched metadata: yes', stdout,
                      'Aktualizr should have run' + stderr.decode() + stdout.decode())


class ImplProvTests(OESelftestTestCase):

    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of luck.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = " aktualizr-ca-implicit-prov "')
        self.append_config('SOTA_DEPLOY_CREDENTIALS = "0"')
        runCmd('bitbake -c cleanall aktualizr aktualizr-ca-implicit-prov')
        self.qemu, self.s = qemu_launch(machine='qemux86-64')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_provisioning(self):
        print('Checking machine name (hostname) of device:')
        stdout, stderr, retcode = self.qemu_command('hostname')
        self.assertEqual(retcode, 0, "Unable to check hostname. " +
                         "Is an ssh daemon (such as dropbear or openssh) installed on the device?")
        machine = get_bb_var('MACHINE', 'core-image-minimal')
        self.assertEqual(stderr, b'', 'Error: ' + stderr.decode())
        # Strip off line ending.
        value = stdout.decode()[:-1]
        self.assertEqual(value, machine,
                         'MACHINE does not match hostname: ' + machine + ', ' + value)

        verifyNotProvisioned(self, machine)

        # Run aktualizr-cert-provider.
        bb_vars = get_bb_vars(['SOTA_PACKED_CREDENTIALS'], 'aktualizr-native')
        creds = bb_vars['SOTA_PACKED_CREDENTIALS']
        bb_vars_prov = get_bb_vars(['STAGING_DIR_HOST', 'libdir'], 'aktualizr-ca-implicit-prov')
        config = bb_vars_prov['STAGING_DIR_HOST'] + bb_vars_prov['libdir'] + '/sota/sota_implicit_prov_ca.toml'

        print('Provisining at root@localhost:%d' % self.qemu.ssh_port)
        akt_native_run(self, 'aktualizr-cert-provider -c {creds} -t root@localhost -p {port} -s -u -r -g {config}'
                       .format(creds=creds, port=self.qemu.ssh_port, config=config))

        verifyProvisioned(self, machine)


class HsmTests(OESelftestTestCase):

    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of luck.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = "aktualizr-hsm-prov"')
        self.append_config('SOTA_DEPLOY_CREDENTIALS = "0"')
        self.append_config('SOTA_CLIENT_FEATURES = "hsm"')
        self.append_config('IMAGE_INSTALL_append = " softhsm-testtoken"')
        runCmd('bitbake -c cleanall aktualizr aktualizr-hsm-prov')
        self.qemu, self.s = qemu_launch(machine='qemux86-64')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_provisioning(self):
        print('Checking machine name (hostname) of device:')
        stdout, stderr, retcode = self.qemu_command('hostname')
        self.assertEqual(retcode, 0, "Unable to check hostname. " +
                         "Is an ssh daemon (such as dropbear or openssh) installed on the device?")
        machine = get_bb_var('MACHINE', 'core-image-minimal')
        self.assertEqual(stderr, b'', 'Error: ' + stderr.decode())
        # Strip off line ending.
        value = stdout.decode()[:-1]
        self.assertEqual(value, machine,
                         'MACHINE does not match hostname: ' + machine + ', ' + value)

        verifyNotProvisioned(self, machine)

        # Verify that HSM is not yet initialized.
        pkcs11_command = 'pkcs11-tool --module=/usr/lib/softhsm/libsofthsm2.so -O'
        stdout, stderr, retcode = self.qemu_command(pkcs11_command)
        self.assertNotEqual(retcode, 0, 'pkcs11-tool succeeded before initialization: ' +
                            stdout.decode() + stderr.decode())
        softhsm2_command = 'softhsm2-util --show-slots'
        stdout, stderr, retcode = self.qemu_command(softhsm2_command)
        self.assertNotEqual(retcode, 0, 'softhsm2-tool succeeded before initialization: ' +
                            stdout.decode() + stderr.decode())

        # Run aktualizr-cert-provider.
        bb_vars = get_bb_vars(['SOTA_PACKED_CREDENTIALS'], 'aktualizr-native')
        creds = bb_vars['SOTA_PACKED_CREDENTIALS']
        bb_vars_prov = get_bb_vars(['STAGING_DIR_NATIVE', 'libdir'], 'aktualizr-hsm-prov')
        config = bb_vars_prov['STAGING_DIR_NATIVE'] + bb_vars_prov['libdir'] + '/sota/sota_hsm_prov.toml'

        akt_native_run(self, 'aktualizr-cert-provider -c {creds} -t root@localhost -p {port} -r -s -u -g {config}'
                       .format(creds=creds, port=self.qemu.ssh_port, config=config))

        # Verify that HSM is able to initialize.
        ran_ok = False
        for delay in [5, 5, 5, 5, 10]:
            sleep(delay)
            p11_out, p11_err, p11_ret = self.qemu_command(pkcs11_command)
            hsm_out, hsm_err, hsm_ret = self.qemu_command(softhsm2_command)
            if p11_ret == 0 and hsm_ret == 0 and hsm_err == b'':
                ran_ok = True
                break
        self.assertTrue(ran_ok, 'pkcs11-tool or softhsm2-tool failed: ' + p11_err.decode() +
                        p11_out.decode() + hsm_err.decode() + hsm_out.decode())
        self.assertIn(b'present token', p11_err, 'pkcs11-tool failed: ' + p11_err.decode() + p11_out.decode())
        self.assertIn(b'X.509 cert', p11_out, 'pkcs11-tool failed: ' + p11_err.decode() + p11_out.decode())
        self.assertIn(b'Initialized:      yes', hsm_out, 'softhsm2-tool failed: ' +
                      hsm_err.decode() + hsm_out.decode())
        self.assertIn(b'User PIN init.:   yes', hsm_out, 'softhsm2-tool failed: ' +
                      hsm_err.decode() + hsm_out.decode())

        # Check that pkcs11 output matches sofhsm output.
        p11_p = re.compile(r'Using slot [0-9] with a present token \((0x[0-9a-f]*)\)\s')
        p11_m = p11_p.search(p11_err.decode())
        self.assertTrue(p11_m, 'Slot number not found with pkcs11-tool: ' + p11_err.decode() + p11_out.decode())
        self.assertGreater(p11_m.lastindex, 0, 'Slot number not found with pkcs11-tool: ' +
                           p11_err.decode() + p11_out.decode())
        hsm_p = re.compile(r'Description:\s*SoftHSM slot ID (0x[0-9a-f]*)\s')
        hsm_m = hsm_p.search(hsm_out.decode())
        self.assertTrue(hsm_m, 'Slot number not found with softhsm2-tool: ' + hsm_err.decode() + hsm_out.decode())
        self.assertGreater(hsm_m.lastindex, 0, 'Slot number not found with softhsm2-tool: ' +
                           hsm_err.decode() + hsm_out.decode())
        self.assertEqual(p11_m.group(1), hsm_m.group(1), 'Slot number does not match: ' +
                         p11_err.decode() + p11_out.decode() + hsm_err.decode() + hsm_out.decode())

        verifyProvisioned(self, machine)


class SecondaryTests(OESelftestTestCase):
    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of luck.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = " aktualizr-auto-prov "')
        self.qemu, self.s = qemu_launch(machine='qemux86-64', imagename='secondary-image')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_secondary_present(self):
        print('Checking aktualizr-secondary is present')
        stdout, stderr, retcode = self.qemu_command('aktualizr-secondary --help')
        self.assertEqual(retcode, 0, "Unable to run aktualizr-secondary --help")
        self.assertEqual(stderr, b'', 'Error: ' + stderr.decode())


class PrimaryTests(OESelftestTestCase):
    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of luck.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = " aktualizr-auto-prov "')
        self.append_config('SOTA_CLIENT_FEATURES = "secondary-network"')
        self.qemu, self.s = qemu_launch(machine='qemux86-64', imagename='primary-image')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_aktualizr_present(self):
        print('Checking aktualizr is present')
        stdout, stderr, retcode = self.qemu_command('aktualizr --help')
        self.assertEqual(retcode, 0, "Unable to run aktualizr --help")
        self.assertEqual(stderr, b'', 'Error: ' + stderr.decode())


class ResourceControlTests(OESelftestTestCase):
    def setUpLocal(self):
        layer = "meta-updater-qemux86-64"
        result = runCmd('bitbake-layers show-layers')
        if re.search(layer, result.output) is None:
            # Assume the directory layout for finding other layers. We could also
            # make assumptions by using 'show-layers', but either way, if the
            # layers we need aren't where we expect them, we are out of luck.
            path = os.path.abspath(os.path.dirname(__file__))
            metadir = path + "/../../../../../"
            self.meta_qemu = metadir + layer
            runCmd('bitbake-layers add-layer "%s"' % self.meta_qemu)
        else:
            self.meta_qemu = None
        self.append_config('MACHINE = "qemux86-64"')
        self.append_config('SOTA_CLIENT_PROV = " aktualizr-auto-prov "')
        self.append_config('IMAGE_INSTALL_append += " aktualizr-resource-control "')
        self.append_config('RESOURCE_CPU_WEIGHT_pn-aktualizr = "1000"')
        self.append_config('RESOURCE_MEMORY_HIGH_pn-aktualizr = "50M"')
        self.append_config('RESOURCE_MEMORY_MAX_pn-aktualizr = "1M"')
        self.qemu, self.s = qemu_launch(machine='qemux86-64')

    def tearDownLocal(self):
        qemu_terminate(self.s)
        if self.meta_qemu:
            runCmd('bitbake-layers remove-layer "%s"' % self.meta_qemu, ignore_status=True)

    def qemu_command(self, command):
        return qemu_send_command(self.qemu.ssh_port, command)

    def test_aktualizr_resource_control(self):
        print('Checking aktualizr was killed')
        ran_ok = False
        for delay in [5, 5, 5, 5]:
            sleep(delay)
            stdout, stderr, retcode = self.qemu_command('systemctl --no-pager show aktualizr')
            if retcode == 0 and b'ExecMainStatus=9' in stdout:
                ran_ok = True
                break
        self.assertTrue(ran_ok, 'Aktualizr was not killed')

        self.assertIn(b'CPUWeight=1000', stdout, 'CPUWeight was not set correctly')
        self.assertIn(b'MemoryHigh=52428800', stdout, 'MemoryHigh was not set correctly')
        self.assertIn(b'MemoryMax=1048576', stdout, 'MemoryMax was not set correctly')

        self.qemu_command('systemctl --runtime set-property aktualizr MemoryMax=')
        self.qemu_command('systemctl restart aktualizr')

        stdout, stderr, retcode = self.qemu_command('systemctl --no-pager show --property=ExecMainStatus aktualizr')
        self.assertIn(b'ExecMainStatus=0', stdout, 'Aktualizr did not restart')

# vim:set ts=4 sw=4 sts=4 expandtab: