import sys
from django.conf import settings
from django.db.backends import creation


def monkey_patch_creation():
    """
    This replaces the test_db creation/deletion methods to allow a persistent
    test db, by prompting the user to either keep or destroy the test database.
    """
    def _create_test_db(self, verbosity, noinput):
        """alternate implementation of _create_test_db that skips test database destroying"""
        suffix = self.sql_table_creation_suffix()

        if self.connection.settings_dict['TEST_NAME']:
            test_database_name = self.connection.settings_dict['TEST_NAME']
        else:
            test_database_name = creation.TEST_DATABASE_PREFIX + self.connection.settings_dict['NAME']

        qn = self.connection.ops.quote_name

        # Create the test database and connect to it. We need to autocommit
        # if the database supports it because PostgreSQL doesn't allow
        # CREATE/DROP DATABASE statements within transactions.
        cursor = self.connection.cursor()
        self.set_autocommit()
        try:
            cursor.execute("CREATE DATABASE %s %s" % (qn(test_database_name), suffix))
        except Exception, e:
            sys.stderr.write("Got an error creating the test database: %s\n" % e)
            confirm = False
            if not noinput:
                confirm = raw_input("Type 'yes' if you would like to try deleting/recreating the test database '%s', or 'no' to continue with the existing database [no]: " % test_database_name)
            if confirm == 'yes':
                try:
                    if verbosity >= 1:
                        print "Destroying old test database..."
                    cursor.execute("DROP DATABASE %s" % qn(test_database_name))
                    if verbosity >= 1:
                        print "Creating test database..."
                    cursor.execute("CREATE DATABASE %s %s" % (qn(test_database_name), suffix))
                except Exception, e:
                    sys.stderr.write("Got an error recreating the test database: %s\n" % e)
                    sys.exit(2)
            elif confirm in ('', 'no') or noinput:
                print "Using existing test database."
            else:
                print "Cancelling tests."
                sys.exit(1)

        return test_database_name

    def destroy_test_db(self, old_database_name, verbosity=1):
        """no-op alternative to destroy_test_db"""

    creation.BaseDatabaseCreation._create_test_db = _create_test_db
    creation.BaseDatabaseCreation.destroy_test_db = destroy_test_db


class ResultPlugin(object):
    """
    Captures the TestResult object for later inspection.

    nose doesn't return the full test result object from any of its runner
    methods.  Pass an instance of this plugin to the TestProgram and use
    ``result`` after running the tests to get the TestResult object.
    """

    name = "result"
    enabled = True

    def finalize(self, result):
        self.result = result


class DjangoSetUpPlugin(object):
    """
    Configures Django to setup and tear down the environment.
    This allows coverage to report on all code imported and used during the
    initialisation of the test runner.
    """
    name = "django setup"
    enabled = True

    def __init__(self, runner):
        super(DjangoSetUpPlugin, self).__init__()
        self.runner = runner
        self.sys_stdout = sys.stdout

    def begin(self):
        """Setup the environment"""
        sys_stdout = sys.stdout
        sys.stdout = self.sys_stdout

        if getattr(settings, 'KEEP_TEST_DB', False):
            monkey_patch_creation()

        self.runner.setup_test_environment()
        self.old_names = self.runner.setup_databases()

        sys.stdout = sys_stdout

    def finalize(self, result):
        """Destroy the environment"""
        self.runner.teardown_databases(self.old_names)
        self.runner.teardown_test_environment()
