from client import ApiClient
from exceptions import *
from suds.sax.element import Element
import sys
import suds
try:
    from swiftclient import Connection
except ImportError:
    from swift.common.client import Connection
import itertools


# Patching some stuff in suds to get it working with SOAP 1.2
suds.bindings.binding.envns = (
    'SOAP-ENV', 'http://www.w3.org/2003/05/soap-envelope')


# WSDL addresses
wsdl_common = 'https://api.oktawave.com/CommonService.svc?wsdl'
wsdl_clients = 'https://api.oktawave.com/ClientsService.svc?wsdl'

# Fixing WSDL to work with suds
ans = ('a', 'http://www.w3.org/2005/08/addressing')


def header(key, value, namespace=ans):
    return Element(key, ns=namespace).setText(value)


def hc_common(method):
    return [
        header('Action', 'http://K2.CloudsFactory/ICommon/' + method),
        header('To', 'https://adamm.cloud.local:450/CommonService.svc')
    ]


def hc_clients(method):
    return [
        header('Action', 'http://K2.CloudsFactory/IClients/' + method),
        header('To', 'https://adamm.cloud.local:450/ClientsService.svc')
    ]

docs_common = [
    'http://schemas.datacontract.org/2004/07/K2.CloudsFactory.Common',
    'http://schemas.microsoft.com/2003/10/Serialization/'
]
docs_clients = [
    'http://schemas.microsoft.com/2003/10/Serialization/',
    'http://schemas.microsoft.com/2003/10/Serialization/Arrays',
    'http://schemas.datacontract.org/2004/07/K2.CloudsFactory.Common',
    'http://schemas.datacontract.org/2004/07/K2.CloudsFactory.Common.Models'
]

DICT = {
    'DB_VM_CATEGORY': 324,
    'MYSQL_TEMPLATE_CATEGORY': 28,
    'POSTGRESQL_TEMPLATE_CATEGORY': 29,
    'UTF8_ENCODING': 549,
    'LATIN2_ENCODING': 550,
    'MYSQL_DB': 325,
    'POSTGRESQL_DB': 326,
    'OCI_CONNECTION_ID': 37,
    'OCI_PAYMENT_ID': 33,
    'OCI_AUTOSCALING_ID': 184,
    'OCI_CLASSES_DICT_ID': 12
}

class OktawaveApi(object):

    def __init__(self, username, password, ocs_username=None, ocs_password=None, debug=False):
        """Initialize the API instance

        Arguments:
        - username (string) - Oktawave account username
        - password (string) - Oktawave account password
        - ocs_username (string) - OCS account username
        - ocs_password (string) - OCS account password
        - debug (bool) - enable debug output?
        """
        self.username = username
        self.password = password
        self.ocs_username = ocs_username
        self.ocs_password = ocs_password
        self.debug = debug

    # HELPER METHODS ###
    # methods starting with "_" will not be autodispatched to client commands
    # ###

    def _d(self, what):
        if self.debug:
            print what

    def _init_common(self):
        """Convenience method to initialize CommonService client"""
        if hasattr(self, 'common'):
            return
        self.common = ApiClient(
            wsdl_common, self.username, self.password, hc_common, docs_common, self.debug)
        self._d(self.common)

    def _init_clients(self):
        """Convenience method to initialize ClientsService client"""
        if hasattr(self, 'clients'):
            return
        self.clients = ApiClient(
            wsdl_clients, self.username, self.password, hc_clients, docs_clients, self.debug)
        self.clients.client.factory.separator('########')
        self._d(self.clients)

    def _logon(self, only_common=False):
        """Initializes CommonService client and calls LogonUser method.

        Returns the User object, as returned by LogonUser.
        Also sets self.client_id for convenience.
        """
        self._init_common()
        if not only_common:
            self._init_clients()
        if hasattr(self, 'client_object'):
            return self.client_object
        try:
            res = self.common.call(
                'LogonUser', self.username, self.password, self._get_machine_ip(), "Oktawave CLI")
        except AttributeError:
            raise OktawaveLoginError()
        self.client_id = res._x003C_Client_x003E_k__BackingField.ClientId
        self.client_object = res
        return res

    def _search_params(self, sp):
        # getting rid of NoneType non-special attributes, required for
        # searchParams
        self._d(sp)
        for param in [m for m in dir(sp) if m[0] != '_']:
            if type(getattr(sp, param)) is not "NoneType":
                delattr(sp, param)
        return sp

    def _dict_names(self, data, field='ItemName'):
        return [getattr(item, field) for item in data if item.LanguageDictId == 2]

    def _dict_item_name(self, data, sep=', ', field='ItemName'):
        return self._dict_names(data.DictionaryItemNames[0], field)[0]

    def _simple_vm_method(self, method, vm_id):
        """Wraps around common simple virtual machine method call pattern"""
        self._logon()
        self.clients.call(method, vm_id, self.client_id)

    def _ocs_prepare(self):
        """Wrapper method for OCS/swift API initialization"""
        # swift_username = self._logon(args, only_common =
        # True)._x003C_Client_x003E_k__BackingField.VmwareFriendlyName
        return Connection(
            'https://ocs-pl.oktawave.com/auth/v1.0', self.ocs_username, self.ocs_password)

    def _find_disk(self, disk_id):
        """Finds a disk (OVS) by id"""
        dsp = self._search_params(self.clients.create('ns3:DisksSearchParams'))
        dsp.ClientId = self.client_id
        disks = [d for d in self.clients.call(
            'GetDisks', dsp)._results[0] if d.ClientHddId == disk_id]
        if len(disks) == 0:
            return None
        res = disks[0]
        if res.VirtualMachineHdds == None:
            res.VirtualMachineHdds = [[]]
        return res

    def _get_machine_ip(self):
        return '127.0.0.1'

    def _oci_class_id(self, class_name):
        """Returns ID of an OCI class with a given name"""
        classes = self.common.call(
            'GetDictionaryItems', DICT['OCI_CLASSES_DICT_ID'], self.client_id)
        name2id = dict([(self._dict_item_name(x), x['DictionaryItemId'])
                       for x in classes[0]])
        self._d(name2id)
        if class_name in name2id:
            return name2id[class_name]
        return 0

    # API methods below ###

    # General / Account ###

    def Account_Settings(self):
        """Print basic settings of the client account

        args is an object containing at least the following fields:
        - username - Oktawave username
        - password - Oktawave client password
        Typically args will be the object returned from argparse.

        """
        self._logon(only_common=True)
        client = self.client_object
        # TODO: probably get more settings
        return {
            'time_zone': client._x003C_TimeZone_x003E_k__BackingField.DisplayName,
            'currency': self._dict_item_name(client._x003C_Currency_x003E_k__BackingField),
            'date_format': self._dict_item_name(client._x003C_DateFormat_x003E_k__BackingField),
            'availability_zone': self._dict_item_name(
                self.common.call('GetDictionaryItemById', client._x003C_AvailabilityZone_x003E_k__BackingField)),
            '24h_clock': client._x003C_Is24HourClock_x003E_k__BackingField,
        }

    def Account_RunningJobs(self):
        self._logon()
        res = self.common.call('GetRunningOperations', self.client_id)
        if str(res) == '':
            return
        for op in res[0]:
            yield {
                'id': op.AsynchronousOperationId,
                'creation_date': op.CreationDate,
                'creation_user_name': op.CreationUserFullName,
                'type': self._dict_item_name(op.OperationType),
                'object_type': self._dict_item_name(op.ObjectType),
                'object_name': op.ObjectName,
                'progress_percent': op.Progress,
                'status': self._dict_item_name(op.Status)
            }

    def Account_Users(self):
        """Print users in client account."""
        self._logon()
        users = self.clients.call('GetClientUsers', self.client_id)
        self._d(users)
        for user in users[0]:
            yield {
                'email': user._x003C_Email_x003E_k__BackingField,
                'name': user._x003C_FullName_x003E_k__BackingField,
            }

    # OCI (VMs) ###

    def OCI_Test(self):
        self._logon()
        self._d(self._oci_class_id('Large'))

    def OCI_TemplateCategories(self):
        """Lists available template categories"""
        self._logon()
        data = self.common.call('GetTemplateCategories', self.client_id)
        self._d(data)

        def _tc_info(tc, parent_id):
            return {
                'id': tc.TemplateCategoryId,
                'name': self._dict_names(
                    tc.TemplateCategoryNames[0], 'CategoryName')[0],
                'description': self._dict_names(
                    tc.TemplateCategoryNames[0], 'CategoryDescription')[0],
                'parent_id': parent_id,
            }

        for tc in data[0]:
            yield _tc_info(tc, None)
            if tc.CategoryChildren is not None:
                for tcc in tc.CategoryChildren[0]:
                    yield _tc_info(tcc, tc.TemplateCategoryId)

    def OCI_Templates(self, category_id, name_filter=''):
        """Lists templates in a category"""
        self._logon()
        data = self.common.call(
            'GetTemplatesByCategory', category_id, None, None, self.client_id)
        if data:
            return dict((template.TemplateId, template.TemplateName)
                       for template in data[0] if name_filter in template.TemplateName)

    def OCI_TemplateInfo(self, template_id):
        """Shows more detailed info about a particular template"""
        self._logon()
        data = self.clients.call('GetTemplate', template_id, self.client_id)

        template_category = '/'.join(self._dict_names(
            data.TemplateCategory.TemplateCategoryNames[0], field='CategoryName'))

        software = ', '.join([
            '/'.join(self._dict_names(s.Software.SoftwareNames[0], field="Name"))
            for s in data.SoftwareList[0]])

        return {
            'template_id': data.TemplateId,
            'template_name': data.TemplateName,
            'template_category': template_category,
            'vm_class_id': data.VMClass.DictionaryItemId,
            'vm_class_name': self._dict_item_name(data.VMClass),
            'system_category_name': self._dict_item_name(data.TemplateSystemCategory),
            'label': data.Name,
            'software': software,
            'eth_count': data.EthernetControllersCount,
            'connection_type': self._dict_item_name(data.ConnectionType),
            'disks': [{
                    'name': hdd.HddName,
                    'capacity_gb': hdd.CapacityGB,
                    'is_primary': hdd.IsPrimary
                } for hdd in data.DiskDrives[0]],
            'description': data.Description
        }

    def OCI_List(self):
        """Lists client's virtual machines"""
        self._logon()
        sp = self._search_params(
            self.clients.create('ns3:VirtualMachineSearchParams'))
        sp.ClientId = self.client_id
        vms = self.clients.call('GetVirtualMachines', sp)
        self._d(vms)
        for vm in vms._results[0]:
            yield {
                'id': vm.VirtualMachineId,
                'name': vm.VirtualMachineName,
                'class_name': self._dict_item_name(vm.VMClass)
            }

    def OCI_Restart(self, oci_id):
        """Restarts given VM"""
        self._simple_vm_method('RestartVirtualMachine', oci_id)

    def OCI_TurnOff(self, oci_id):
        """Turns given VM off"""
        self._simple_vm_method('TurnoffVirtualMachine', oci_id)

    def OCI_TurnOn(self, oci_id):
        """Turns given virtual machine on"""
        self._simple_vm_method('TurnOnVirtualMachine', oci_id)

    def OCI_Delete(self, oci_id):
        """Deletes given virtual machine"""
        self._simple_vm_method('DeleteVirtualMachine', oci_id)

    def OCI_Logs(self, oci_id):
        """Shows virtual machine logs"""
        self._logon()
        sp = self._search_params(
            self.clients.create('ns3:VirtualMachineHistoriesSearchParams'))
        sp.VirtualMachineId = oci_id
        sp.PageSize = 100
        sp.SortingDirection = 'Descending'
        data = self.clients.call(
            'GetVirtualMachineHistories', sp, self.client_id)
        self._d(data)
        for op in data._results[0]:
            yield {
                'time': op.CreationDate,
                'type': self._dict_item_name(op.OperationType),
                'user_name': op.CreationUser.FullName,
                'status': self._dict_item_name(op.Status)
            }

    def OCI_Settings(self, oci_id):
        """Shows basic VM settings (IP addresses, OS, names, autoscaling etc.)"""
        self._logon()
        data = self.clients.call(
            'GetVirtualMachineById', oci_id, self.client_id)

        res = {
            'autoscaling': self._dict_item_name(data.AutoScalingType),
            'connection_type': self._dict_item_name(data.ConnectionType),
            'cpu_mhz': data.CpuMhz,
            'cpu_usage_mhz': data.CpuMhzUsage,
            'creation_date': data.CreationDate,
            'creation_user_name': data.CreationUserSimple.FullName,
            'iops_usage': data.IopsUsage,
            'last_change_date': data.LastChangeDate,
            'payment_type': self._dict_item_name(data.PaymentType),
            'memory_mb': data.RamMB,
            'memory_usage_mb': data.RamMBUsage,
            'status': self._dict_item_name(data.Status),
            'name': data.VirtualMachineName,
            'vm_class_name': self._dict_item_name(data.VMClass),
            'disks': [{
                'name': disk.ClientHdd.HddName,
                'capacity_gb': disk.ClientHdd.CapacityGB,
                'creation_date': disk.ClientHdd.CreationDate,
                'creation_user_name': disk.ClientHdd.CreationUser.FullName,
                'is_primary': disk.IsPrimary
            } for disk in data.DiskDrives[0]],
            'ips': [{
                'ipv4': ip.Address,
                'ipv6': ip.AddressV6,
                'creation_date': ip.CreationDate,
                'dhcp_branch': ip.DhcpBranch,
                'gateway': ip.Gateway,
                'status': self._dict_item_name(ip.IPStatus),
                'last_change_date': ip.LastChangeDate,
                'macaddr': ip.MacAddress,
            } for ip in data.IPs[0]],
            'vlans': [],
        }
        if data.PrivateIpv4:
            res['vlans'] = [{
                'ipv4': vlan.PrivateIpAddress,
                'creation_date': vlan.CreationDate,
                'macaddr': vlan.MacAddress,
            } for vlan in data.PrivateIpv4[0]]

        return res

    def OCI_Create(self, name, template, oci_class=None, forced_type='Machine', db_type=None):
        """Creates a new instance from template"""
        self._logon()
        template = self.clients.call(
            'GetTemplate', template, self.client_id)
        oci_class_id = None
        if oci_class:
            oci_class_id = self._oci_class_id(oci_class)
            if not oci_class_id:
                raise OktawaveOCIClassNotFound()
        self.clients.call('CreateVirtualMachine',
                          template,
                          None,
                          None,
                          name,
                          oci_class_id,
                          None,
                          DICT['OCI_PAYMENT_ID'],
                          DICT['OCI_CONNECTION_ID'],
                          self.client_id,
                          None,
                          forced_type,
                          db_type,
                          None,
                          DICT['OCI_AUTOSCALING_ID']
                          )

    def OCI_Clone(self, oci_id, name, clonetype):
        """Clones a VM"""
        self._logon()
        self.clients.call(
            'CloneVirtualMachine', oci_id, name, clonetype, self.client_id)

    # OVS (disks) ###

    def OVS_List(self):
        """Lists disks"""
        self._logon()
        dsp = self._search_params(self.clients.create('ns3:DisksSearchParams'))
        dsp.ClientId = self.client_id
        data = self.clients.call('GetDisks', dsp)
        for disk in data._results[0]:
            if disk.VirtualMachineHdds is None:
                vms = []
            else:
                vms = [{
                    'id': vm.VirtualMachine.VirtualMachineId,
                    'name': vm.VirtualMachine.VirtualMachineName,
                } for vm in disk.VirtualMachineHdds[0]]
            yield {
                'id': disk.ClientHddId,
                'name': disk.HddName,
                'tier': self._dict_item_name(disk.HddStandard),
                'capacity_gb': disk.CapacityGB,
                'used_gb': disk.UsedCapacityGB,
                'is_shared': disk.IsShared,
                'vms': vms,
            }

    def OVS_Delete(self, ovs_id):
        """Deletes a disk"""
        self._logon()
        res = self.clients.call('DeleteDisk', ovs_id, self.client_id)
        if not res:
            raise OktawaveOVSDeleteError()

    def OVS_Create(self, name, capacity_gb, tier, shared):
        """Adds a disk"""
        self._logon()
        disk = self.clients.create('ns3:ClientHddWithVMIds')
        disk.CapacityGB = capacity_gb
        disk.HddName = name
        disk.HddStandardId = 47 + int(tier)
        disk.IsShared = shared
        disk.PaymentTypeId = 37
        disk.VirtualMachineIds = ''  # this seems to solve the empty-array error problem, but certainly is not nice
        self.clients.call('CreateDisk', disk, self.client_id)

    def OVS_Map(self, ovs_id, oci_id):
        """Maps a disk into an instance"""
        self._logon()
        disk = self._find_disk(ovs_id)
        if disk is None:
            raise OktawaveOVSNotFoundError()

        vms = [
            vm.VirtualMachine.VirtualMachineId for vm in disk.VirtualMachineHdds[0]]
        if oci_id in vms:
            raise OktawaveOVSMappedError()

        disk_mod = self.clients.create('ns3:ClientHddWithVMIds')
        for attr in ['CapacityGB', 'ClientHddId', 'HddName', 'IsShared']:
            setattr(disk_mod, attr, getattr(disk, attr))
        disk_mod.HddStandardId = disk.HddStandard.DictionaryItemId
        disk_mod.PaymentTypeId = disk.PaymentType.DictionaryItemId
        disk_mod.VirtualMachineIds = self.clients.create('ns6:ArrayOfint')
        disk_mod.VirtualMachineIds[0].extend(vms + [oci_id])
        res = self.clients.call('UpdateDisk', disk_mod, self.client_id)
        if not res:
            raise OktawaveOVSMapError()

    def OVS_Unmap(self, ovs_id, oci_id):
        """Unmaps a disk from an instance"""
        self._logon()
        disk = self._find_disk(ovs_id)
        if disk is None:
            raise OktawaveOVSNotFoundError()

        vms = [
            vm.VirtualMachine.VirtualMachineId for vm in disk.VirtualMachineHdds[0]]
        if oci_id not in vms:
            raise OktawaveOVSUnmappedError()

        disk_mod = self.clients.create('ns3:ClientHddWithVMIds')
        for attr in ['CapacityGB', 'ClientHddId', 'HddName', 'IsShared']:
            setattr(disk_mod, attr, getattr(disk, attr))
        disk_mod.HddStandardId = disk.HddStandard.DictionaryItemId
        disk_mod.PaymentTypeId = disk.PaymentType.DictionaryItemId
        disk_mod.VirtualMachineIds = self.clients.create('ns6:ArrayOfint')
        disk_mod.VirtualMachineIds[0].extend(
            [vm for vm in vms if vm != oci_id])
        if len(disk_mod.VirtualMachineIds[0]) == 0:
            disk_mod.VirtualMachineIds = ''
        res = self.clients.call('UpdateDisk', disk_mod, self.client_id)
        if not res:
            raise OktawaveOVSUnmapError()

    # ORDB (databases) ###

    def ORDB_List(self):
        """Lists databases"""
        self._logon()
        sp = self._search_params(
            self.clients.create('ns3:DatabaseInstanceSearchParams'))
        sp.ClientId = self.client_id
        data = self.clients.call('GetDatabaseInstances', sp)
        if not data._results:
            return
        for db in data._results[0]:
            yield {
                'id': db.VirtualMachineId,
                'name': db.VirtualMachineName,
                'type': self._dict_item_name(db.DatabaseType),
                'size': db.Size,
                'available_space': db.AvailableSpace,
            }

    def ORDB_TurnOn(self, oci_id):
        """Turns a database on"""
        self._simple_vm_method('TurnOnVirtualMachine', oci_id)

    def ORDB_TurnOff(self, oci_id):
        """Turns a database off"""
        self._simple_vm_method('TurnoffVirtualMachine', oci_id)

    def ORDB_Restart(self, oci_id):
        """Restarts a database"""
        self._simple_vm_method('RestartVirtualMachine', oci_id)

    ORDB_Clone = OCI_Clone

    def ORDB_Delete(self, oci_id, db_name=None):
        """Deletes a database or VM"""
        self._logon()
        if db_name is None:
            self._simple_vm_method('DeleteVirtualMachine', oci_id)
        else:
            self.clients.call(
                'DeleteDatabase', oci_id, db_name, self.client_id)

    ORDB_Logs = OCI_Logs

    def ORDB_LogicalDatabases(self, oci_id):
        """Shows logical databases"""
        self._logon()
        sp = self._search_params(
            self.clients.create('ns3:DatabaseInstanceSearchParams'))
        sp.ClientId = self.client_id
        data = self.clients.call('GetDatabaseInstances', sp)
        if not data._results:
            return

        for vm in data._results[0]:
            if oci_id is not None and str(vm.VirtualMachineId) != str(oci_id):
                continue

            for db in vm.Databases[0]:
                yield {
                    'id': db.VirtualMachineId,
                    'name': db.DatabaseName,
                    'type': self._dict_item_name(db.DatabaseType),
                    'encoding': db.Encoding,
                    'is_running': db.IsRunning,
                    'qps': db.QPS,
                    'size': db.Size
                }

    ORDB_Settings = OCI_Settings

    def ORDB_Create(self, name, template, oci_class=None):
        """Creates a database VM"""
        self._logon()
        data = self.clients.call('GetTemplate', template, self.client_id)
        if str(data.TemplateType.DictionaryItemId) != str(DICT['DB_VM_CATEGORY']):
            raise OktawaveORDBInvalidTemplateError()
        self.OCI_Create(name, template,
                        forced_type='Database', db_type=data.DatabaseType.DictionaryItemId)

    def ORDB_GlobalSettings(self, oci_id):
        """Shows global database engine settings"""
        self._logon()
        data = self.clients.call('GetDatabaseConfig', oci_id, self.client_id)
        if not data:
            return

        for item in data[0]:
            yield {
                'name': item.Name,
                'value': item.Value
            }

    def ORDB_CreateLogicalDatabase(self, oci_id, name, encoding):
        """Creates a new logical database within an instance"""
        self._logon()
        self.clients.call('CreateDatabase', oci_id, name, DICT[
                          encoding.upper() + '_ENCODING'], self.client_id)

    def ORDB_BackupLogicalDatabase(self, oci_id, name):
        """Creates a backup of logical database"""
        self._logon()
        self.clients.call('BackupDatabase', oci_id, name, self.client_id)

    def ORDB_MoveLogicalDatabase(self, oci_id_from, oci_id_to, name):
        """Moves a logical database"""
        self._logon()
        self.clients.call(
            'MoveDatabase', oci_id_from, oci_id_to, name, self.client_id)

    def ORDB_Backups(self):
        """Lists logical database backups"""
        self._logon()
        mysql_data = self.clients.call(
            'GetBackups', DICT['MYSQL_DB'], self.client_id) or [[]]
        pgsql_data = self.clients.call(
            'GetBackups', DICT['POSTGRESQL_DB'], self.client_id) or [[]]

        for db in mysql_data[0]:
            yield {
                'file_name': b._x003C_Name_x003E_k__BackingField,
                'type': 'MySQL',
                'path': b._x003C_ContainerName_x003E_k__BackingField +
                    "/" + b._x003C_FullPath_x003E_k__BackingField
            }

        for db in pgsql_data[0]:
            yield {
                'file_name': b._x003C_Name_x003E_k__BackingField,
                'type': 'PostgreSQL',
                'path': b._x003C_ContainerName_x003E_k__BackingField +
                    "/" + b._x003C_FullPath_x003E_k__BackingField
            }

    def ORDB_RestoreLogicalDatabase(self, oci_id, name, backup_file):
        """Restores a database from backup"""
        self._logon()
        self.clients.call('RestoreDatabase', oci_id,
                          name, backup_file, self.client_id)
