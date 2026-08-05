package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp46 exclude-deleted, UPDATED by cp52: the v2 identity key still ignores owners flagged deleted, so
 *  a same-identity create after a deleted owner still succeeds. */
@Tag("cp46")
class Cp46Tests extends AcceptanceBase {

	@Test
	void coreDeletedOwnerDoesNotBlock() throws Exception {
		ObjectNode a = structuredOwner();
		a.put("deleted", true);
		createOwnerOk(a);
		ObjectNode b = a.deepCopy();
		b.remove("deleted");
		createOwner(b).andExpect(status().is2xxSuccessful());
	}
}
