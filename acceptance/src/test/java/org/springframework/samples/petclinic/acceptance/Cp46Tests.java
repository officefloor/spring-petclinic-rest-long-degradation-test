package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp46 exclude-deleted: DELETE /api/owners/{id} soft-deletes (flags 'deleted' true, retains the
 *  record); the create endpoint's duplicate/identity checks then ignore deleted owners. */
@Tag("cp46")
class Cp46Tests extends AcceptanceBase {

	@Test
	void coreSoftDeleteFlagsAndRetains() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(status().isOk()).andExpect(jsonPath("$.deleted").value(false));
		deleteOwner(id);
		getOwner(id).andExpect(status().isOk()).andExpect(jsonPath("$.deleted").value(true));
	}

	@Test
	void coreDeletedOwnerIgnoredByDuplicateCheck() throws Exception {
		ObjectNode a = structuredOwner();
		int id = createOwnerOk(a);
		deleteOwner(id); // A is soft-deleted
		createOwner(a.deepCopy()).andExpect(status().is2xxSuccessful()); // only match is deleted -> allowed
	}
}
