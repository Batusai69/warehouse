# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from pyramid.httpexceptions import HTTPSeeOther

from warehouse.packaging.interfaces import IDocsStorage
from warehouse.packaging.models import JournalEntry
from warehouse.tasks import task


@task(bind=True, ignore_result=True, acks_late=True)
def remove_documentation(task, request, project_name):
    request.log.info("Removing documentation for %s", project_name)
    storage = request.find_service(IDocsStorage)
    try:
        storage.remove_by_prefix(f"{project_name}/")
    except Exception as exc:
        task.retry(exc=exc)


PROJECT_NAME_RE = re.compile(
    r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", re.IGNORECASE
)


def confirm_project(
    project,
    request,
    fail_route,
    field_name="confirm_project_name",
    error_message="Could not delete project",
):
    confirm = request.POST.get(field_name, "").strip()
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                project_name=project.normalized_name,
            )
        )

    project_name = project.name.strip()
    if confirm != project_name:
        request.session.flash(
            f"{error_message} - {confirm!r} is not the same as {project_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                project_name=project.normalized_name,
            )
        )


def remove_project(project, request, flash=True):
    # TODO: We don't actually delete files from the data store. We should add
    #       some kind of garbage collection at some point.

    request.db.add(
        JournalEntry(
            name=project.name,
            action="remove project",
            submitted_by=request.user,
        )
    )

    request.db.delete(project)
    request.db.flush()  # flush db now so we can repeat if necessary

    if flash:
        request.session.flash(f"Deleted the project {project.name!r}", queue="success")


def destroy_docs(project, request, flash=True):
    request.task(remove_documentation).delay(project.name)

    project.has_docs = False

    if flash:
        request.session.flash(
            f"Deleted docs for project {project.name!r}", queue="success"
        )
