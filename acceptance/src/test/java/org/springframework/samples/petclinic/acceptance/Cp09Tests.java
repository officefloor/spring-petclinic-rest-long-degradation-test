package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** customer-code: Assign 'customerCode' formatted '<LAST3>-<NNNN>' where LAST3 is the upper-cased first thre... */
@Tag("cp09")
class Cp09Tests extends AcceptanceBase {

	@Test
	void coreFormatAndGlobalSequence() throws Exception {
		ObjectNode a = ownerNode(); a.put("lastName", "smithers");
		int ida = createOwnerOk(a);
		ObjectNode b = ownerNode(); b.put("lastName", "jones");
		int idb = createOwnerOk(b);
		String ca = fetchOwner(ida).get("customerCode").asText();
		String cb = fetchOwner(idb).get("customerCode").asText();
		assertTrue(ca.startsWith("SMI-"), ca);
		assertTrue(cb.startsWith("JON-"), cb);
		assertEquals(Integer.parseInt(ca.substring(4)) + 1, Integer.parseInt(cb.substring(4)));
	}
}
