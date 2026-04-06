"""Tests for --skip-existing flag behavior."""
import pytest
from unittest.mock import Mock, patch, call
from click.testing import CliRunner

from src.cli.commands import migrate
from src.core.config import MigrationConfig
from src.core.migrator import Migrator
from src.utils.logger import Logger


class TestSkipExistingCLI:
    """Test that --skip-existing CLI flag is parsed and passed correctly."""

    @pytest.fixture
    def mock_migrator(self):
        """Mock the Migrator class to prevent actual execution."""
        with patch('src.cli.commands.Migrator') as mock:
            mock.return_value.run.return_value = None
            yield mock

    def test_skip_existing_flag_passed_to_config(self, mock_migrator):
        """Test that --skip-existing flag is passed to MigrationConfig."""
        runner = CliRunner()
        env = {
            'SOURCE_ORG': 'test-org',
            'SOURCE_REPO': 'test-repo',
            'TARGET_ORG': 'target-org',
            'TARGET_REPO': 'target-repo',
            'GITHUB_TOKEN': 'github-token',
        }
        result = runner.invoke(migrate, ['--skip-existing'], env=env)
        assert result.exit_code == 0
        config = mock_migrator.call_args[0][0]
        assert config.skip_existing is True

    def test_skip_existing_default_is_false(self, mock_migrator):
        """Test that skip_existing defaults to False when flag is not provided."""
        runner = CliRunner()
        env = {
            'SOURCE_ORG': 'test-org',
            'SOURCE_REPO': 'test-repo',
            'TARGET_ORG': 'target-org',
            'TARGET_REPO': 'target-repo',
            'GITHUB_TOKEN': 'github-token',
        }
        result = runner.invoke(migrate, [], env=env)
        assert result.exit_code == 0
        config = mock_migrator.call_args[0][0]
        assert config.skip_existing is False

    def test_skip_existing_via_env_var(self, mock_migrator):
        """Test that SKIP_EXISTING env var enables the flag."""
        runner = CliRunner()
        env = {
            'SOURCE_ORG': 'test-org',
            'SOURCE_REPO': 'test-repo',
            'TARGET_ORG': 'target-org',
            'TARGET_REPO': 'target-repo',
            'GITHUB_TOKEN': 'github-token',
            'SKIP_EXISTING': 'true',
        }
        result = runner.invoke(migrate, [], env=env)
        assert result.exit_code == 0
        config = mock_migrator.call_args[0][0]
        assert config.skip_existing is True


def _make_mock_logger():
    logger = Mock(spec=Logger)
    logger.debug = Mock()
    logger.info = Mock()
    logger.warn = Mock()
    logger.error = Mock()
    logger.success = Mock()
    return logger


def _make_mock_api():
    """Create a mock GitHubClient with all common methods."""
    api = Mock()
    api.get_rate_limit_info.return_value = {
        'remaining': 5000,
        'limit': 5000,
        'reset_time': 9999999999,
        'reset_in_seconds': 3600,
    }
    return api


class TestSkipExistingRepoMigration:
    """Test skip-existing filtering during repo-to-repo migration."""

    def _make_migrator(self, skip_existing: bool):
        config = MigrationConfig(
            source_org="source-org",
            source_repo="source-repo",
            target_org="target-org",
            target_repo="target-repo",
            source_pat="source-pat",
            target_pat="target-pat",
            skip_existing=skip_existing,
        )
        logger = _make_mock_logger()
        migrator = Migrator.__new__(Migrator)
        migrator.config = config
        migrator.log = logger
        migrator.source_api = _make_mock_api()
        migrator.target_api = _make_mock_api()
        migrator._validate_permissions = Mock()
        migrator._wait_for_rate_limit_reset = Mock()
        migrator._check_rate_limits = Mock(return_value=True)
        migrator._recreate_environments = Mock()
        migrator._get_workflow_run_url = Mock(return_value="")
        return migrator

    def test_skip_existing_filters_repo_secrets(self):
        """Test that repo secrets already in target are excluded from migration."""
        migrator = self._make_migrator(skip_existing=True)

        # Source has 3 secrets; target already has SECRET_B
        migrator.source_api.list_repo_secrets.return_value = ['SECRET_A', 'SECRET_B', 'SECRET_C']
        migrator.target_api.list_repo_secrets.return_value = ['SECRET_B']
        migrator.source_api.list_all_environments_with_secrets.return_value = {}
        migrator.source_api.get_default_branch.return_value = 'main'
        migrator.source_api.get_commit_sha.return_value = 'abc123'
        migrator.source_api.delete_branch = Mock()
        migrator.source_api.create_branch = Mock()
        migrator.source_api.create_repo_secret = Mock()
        migrator.source_api.create_file = Mock()

        with patch('src.core.migrator.generate_workflow', return_value='workflow-content') as mock_gen:
            migrator.run()

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        repo_secrets = kwargs['repo_secrets']
        assert 'SECRET_A' in repo_secrets
        assert 'SECRET_C' in repo_secrets
        assert 'SECRET_B' not in repo_secrets

    def test_skip_existing_logs_skipped_secrets(self):
        """Test that skipped secrets are logged."""
        migrator = self._make_migrator(skip_existing=True)

        migrator.source_api.list_repo_secrets.return_value = ['SECRET_A', 'SECRET_B']
        migrator.target_api.list_repo_secrets.return_value = ['SECRET_B']
        migrator.source_api.list_all_environments_with_secrets.return_value = {}
        migrator.source_api.get_default_branch.return_value = 'main'
        migrator.source_api.get_commit_sha.return_value = 'abc123'
        migrator.source_api.delete_branch = Mock()
        migrator.source_api.create_branch = Mock()
        migrator.source_api.create_repo_secret = Mock()
        migrator.source_api.create_file = Mock()

        with patch('src.core.migrator.generate_workflow', return_value='workflow-content'):
            migrator.run()

        # Verify that the info log mentioned the skipped secret
        log_calls = [str(c) for c in migrator.log.info.call_args_list]
        skipped_logged = any('SECRET_B' in c for c in log_calls)
        assert skipped_logged

    def test_no_skip_existing_migrates_all_secrets(self):
        """Test that all secrets are migrated when --skip-existing is not set."""
        migrator = self._make_migrator(skip_existing=False)

        migrator.source_api.list_repo_secrets.return_value = ['SECRET_A', 'SECRET_B']
        migrator.source_api.list_all_environments_with_secrets.return_value = {}
        migrator.source_api.get_default_branch.return_value = 'main'
        migrator.source_api.get_commit_sha.return_value = 'abc123'
        migrator.source_api.delete_branch = Mock()
        migrator.source_api.create_branch = Mock()
        migrator.source_api.create_repo_secret = Mock()
        migrator.source_api.create_file = Mock()

        with patch('src.core.migrator.generate_workflow', return_value='workflow-content') as mock_gen:
            migrator.run()

        mock_gen.assert_called_once()
        call_args = mock_gen.call_args
        # target_api.list_repo_secrets should NOT be called (no skip_existing check)
        migrator.target_api.list_repo_secrets.assert_not_called()

        _, kwargs = call_args
        repo_secrets = kwargs['repo_secrets']
        assert 'SECRET_A' in repo_secrets
        assert 'SECRET_B' in repo_secrets

    def test_skip_existing_filters_environment_secrets(self):
        """Test that environment secrets already in target env are skipped."""
        migrator = self._make_migrator(skip_existing=True)

        migrator.source_api.list_repo_secrets.return_value = ['REPO_SECRET']
        migrator.target_api.list_repo_secrets.return_value = []
        # Source has env 'prod' with ENV_SECRET_A and ENV_SECRET_B
        migrator.source_api.list_all_environments_with_secrets.return_value = {
            'prod': ['ENV_SECRET_A', 'ENV_SECRET_B']
        }
        # Target already has ENV_SECRET_B in prod
        migrator.target_api.list_environment_secrets.return_value = ['ENV_SECRET_B']
        migrator.source_api.get_default_branch.return_value = 'main'
        migrator.source_api.get_commit_sha.return_value = 'abc123'
        migrator.source_api.delete_branch = Mock()
        migrator.source_api.create_branch = Mock()
        migrator.source_api.create_repo_secret = Mock()
        migrator.source_api.create_file = Mock()

        with patch('src.core.migrator.generate_workflow', return_value='workflow-content') as mock_gen:
            migrator.run()

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        env_secrets = kwargs['env_secrets']
        assert 'ENV_SECRET_A' in env_secrets.get('prod', [])
        assert 'ENV_SECRET_B' not in env_secrets.get('prod', [])

    def test_skip_existing_all_secrets_present_stops_migration(self):
        """Test migration stops gracefully when all secrets already exist in target."""
        migrator = self._make_migrator(skip_existing=True)

        migrator.source_api.list_repo_secrets.return_value = ['SECRET_A']
        migrator.target_api.list_repo_secrets.return_value = ['SECRET_A']
        migrator.source_api.list_all_environments_with_secrets.return_value = {}

        with patch('src.core.migrator.generate_workflow') as mock_gen:
            migrator.run()

        # Workflow should not be generated if no secrets left after filtering
        mock_gen.assert_not_called()


class TestSkipExistingOrgMigration:
    """Test skip-existing filtering during org-to-org migration."""

    def _make_migrator(self, skip_existing: bool):
        config = MigrationConfig(
            source_org="source-org",
            source_repo="source-repo",
            target_org="target-org",
            source_pat="source-pat",
            target_pat="target-pat",
            org_to_org=True,
            skip_existing=skip_existing,
        )
        logger = _make_mock_logger()
        migrator = Migrator.__new__(Migrator)
        migrator.config = config
        migrator.log = logger
        migrator.source_api = _make_mock_api()
        migrator.target_api = _make_mock_api()
        migrator._validate_org_permissions = Mock()
        migrator._wait_for_rate_limit_reset = Mock()
        return migrator

    def test_skip_existing_filters_org_secrets(self):
        """Test that org secrets already in target org are excluded from migration."""
        migrator = self._make_migrator(skip_existing=True)

        # Source has ORG_SECRET_A and ORG_SECRET_B; target already has ORG_SECRET_B
        migrator.source_api.get_org_secrets_with_scope.return_value = {
            'ORG_SECRET_A': {'visibility': 'all', 'selected_repositories': []},
            'ORG_SECRET_B': {'visibility': 'all', 'selected_repositories': []},
        }
        migrator.target_api.list_org_secrets.return_value = ['ORG_SECRET_B']
        migrator.target_api.get_matching_repos.return_value = []
        migrator.source_api.create_repo_secret = Mock()

        source_repo_mock = Mock()
        source_repo_mock.default_branch = 'main'
        main_ref = Mock()
        main_ref.object.sha = 'abc123'
        source_repo_mock.get_git_ref.return_value = main_ref
        source_repo_mock.create_git_ref = Mock()
        source_repo_mock.create_file = Mock()
        migrator.source_api.client = Mock()
        migrator.source_api.client.get_repo.return_value = source_repo_mock

        with patch('src.core.migrator.generate_workflow', return_value='workflow-content') as mock_gen:
            migrator.run()

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        org_secrets = kwargs['org_secrets']
        assert 'ORG_SECRET_A' in org_secrets
        assert 'ORG_SECRET_B' not in org_secrets

    def test_no_skip_existing_migrates_all_org_secrets(self):
        """Test that all org secrets are migrated when --skip-existing is not set."""
        migrator = self._make_migrator(skip_existing=False)

        migrator.source_api.get_org_secrets_with_scope.return_value = {
            'ORG_SECRET_A': {'visibility': 'all', 'selected_repositories': []},
            'ORG_SECRET_B': {'visibility': 'all', 'selected_repositories': []},
        }
        migrator.target_api.get_matching_repos.return_value = []
        migrator.source_api.create_repo_secret = Mock()

        source_repo_mock = Mock()
        source_repo_mock.default_branch = 'main'
        main_ref = Mock()
        main_ref.object.sha = 'abc123'
        source_repo_mock.get_git_ref.return_value = main_ref
        source_repo_mock.create_git_ref = Mock()
        source_repo_mock.create_file = Mock()
        migrator.source_api.client = Mock()
        migrator.source_api.client.get_repo.return_value = source_repo_mock

        with patch('src.core.migrator.generate_workflow', return_value='workflow-content') as mock_gen:
            migrator.run()

        # target_api.list_org_secrets should NOT be called
        migrator.target_api.list_org_secrets.assert_not_called()

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        org_secrets = kwargs['org_secrets']
        assert 'ORG_SECRET_A' in org_secrets
        assert 'ORG_SECRET_B' in org_secrets

    def test_skip_existing_all_org_secrets_present_stops_migration(self):
        """Test org migration stops gracefully when all org secrets already exist."""
        migrator = self._make_migrator(skip_existing=True)

        migrator.source_api.get_org_secrets_with_scope.return_value = {
            'ORG_SECRET_A': {'visibility': 'all', 'selected_repositories': []},
        }
        migrator.target_api.list_org_secrets.return_value = ['ORG_SECRET_A']

        with patch('src.core.migrator.generate_workflow') as mock_gen:
            migrator.run()

        # Workflow should not be generated if all org secrets already exist
        mock_gen.assert_not_called()

