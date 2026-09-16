package admission

import (
	"context"
	"errors"
	"regexp"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

func TestPostgresStorePersistsAdmissionProjectionAndOutboxInOneTransaction(t *testing.T) {
	database, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("create sql mock: %v", err)
	}
	defer database.Close()

	store := NewPostgresStore(database)
	now := time.Date(2026, time.September, 15, 12, 0, 0, 0, time.UTC)
	task := Task{
		TaskID:         "task-1",
		OrganizationID: "org-a",
		ProjectID:      "demo",
		Repository:     "https://example.test/demo",
		Objective:      "Run tests",
		Actor:          "hermes",
		Branch:         "main",
		Worktree:       "C:/work/demo",
		Criteria:       []string{"tests pass"},
	}

	mock.ExpectBegin()
	mock.ExpectExec(regexp.QuoteMeta("INSERT INTO gateway.admissions")).
		WithArgs("admission-1", "org-a", "demo", "task-1", "request-1", "hash-1", sqlmock.AnyArg(), "accepted", now).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec(regexp.QuoteMeta("INSERT INTO gateway.task_projection")).
		WithArgs("org-a", "demo", "task-1", sqlmock.AnyArg(), "accepted", now).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec(regexp.QuoteMeta("INSERT INTO gateway.outbox")).
		WithArgs("event-1", "task.admitted.v1", "org-a", "demo", "task-1", sqlmock.AnyArg(), now).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectCommit()

	result, err := store.Admit(context.Background(), task, "request-1", "hash-1", fixedIDs("admission-1", "event-1"), now)
	if err != nil {
		t.Fatalf("admit task: %v", err)
	}
	if result != (Admission{AdmissionID: "admission-1", TaskID: "task-1", Status: "accepted"}) {
		t.Fatalf("unexpected admission: %#v", result)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unmet database expectations: %v", err)
	}
}

func TestPostgresStoreRejectsAConflictingTaskIDWithoutLeavingAnAdmissionRow(t *testing.T) {
	database, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("create sql mock: %v", err)
	}
	defer database.Close()

	store := NewPostgresStore(database)
	task := Task{
		TaskID:         "task-1",
		OrganizationID: "org-a",
		ProjectID:      "demo",
		Repository:     "repo",
		Objective:      "Deploy",
		Actor:          "hermes",
		Branch:         "main",
		Worktree:       "C:/work/demo",
		Criteria:       []string{"deploy succeeds"},
	}

	mock.ExpectBegin()
	mock.ExpectExec(regexp.QuoteMeta("INSERT INTO gateway.admissions")).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec(regexp.QuoteMeta("INSERT INTO gateway.task_projection")).
		WillReturnResult(sqlmock.NewResult(1, 0))
	mock.ExpectQuery(regexp.QuoteMeta("SELECT request_hash, admission_id, status")).
		WithArgs("org-a", "task-1", "request-2").
		WillReturnRows(sqlmock.NewRows([]string{"request_hash", "admission_id", "status"}).
			AddRow("hash-existing", "admission-existing", "accepted"))
	mock.ExpectRollback()

	_, err = store.Admit(
		context.Background(), task, "request-2", "hash-new", fixedIDs("admission-new", "event-new"), time.Now().UTC(),
	)
	if !errors.Is(err, ErrTaskConflict) {
		t.Fatalf("expected task conflict, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unmet database expectations: %v", err)
	}
}

func TestPostgresStoreReadsTheTaskProjectionByOrganization(t *testing.T) {
	database, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("create sql mock: %v", err)
	}
	defer database.Close()

	store := NewPostgresStore(database)
	mock.ExpectQuery(regexp.QuoteMeta("SELECT payload FROM gateway.task_projection")).
		WithArgs("org-a", "task-1").
		WillReturnRows(sqlmock.NewRows([]string{"payload"}).AddRow(`{
            "schema_version":"1.0", "task_id":"task-1", "organization_id":"org-a",
            "project_id":"demo", "repository":"repo", "objective":"Run tests",
            "actor":"hermes", "branch":"main", "worktree":"C:/work/demo",
            "acceptance_criteria":["tests pass"], "state":"accepted",
            "created_at":"2026-09-15T12:00:00Z"
        }`))

	task, err := store.GetTask(context.Background(), "org-a", "task-1")
	if err != nil {
		t.Fatalf("read task projection: %v", err)
	}
	if task.TaskID != "task-1" || task.State != "accepted" {
		t.Fatalf("unexpected task projection: %#v", task)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unmet database expectations: %v", err)
	}
}

func fixedIDs(ids ...string) func() string {
	position := 0
	return func() string {
		value := ids[position]
		position++
		return value
	}
}
