package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp46 exclude-deleted: duplicate/identity checks ignore owners flagged 'deleted' true, so a
 *  normally-blocking duplicate is allowed when the only match is a deleted owner. Create a deleted
 *  owner, then a same-identity owner, which must succeed. (Relies on the create request accepting a
 *  'deleted' flag -- the only soft-delete path the single endpoint exposes.) */
@Tag("cp46")
class Cp46Tests extends AcceptanceBase {

	@Test
	void coreIgnoresDeletedOnDuplicate() throws Exception {
		ObjectNode a = structuredOwner();
		a.put("deleted", true);
		createOwnerOk(a);
		ObjectNode b = a.deepCopy(); // same identity (telephone / lastName / postcode)
		b.remove("deleted");
		createOwner(b).andExpect(status().is2xxSuccessful());
	}
}
