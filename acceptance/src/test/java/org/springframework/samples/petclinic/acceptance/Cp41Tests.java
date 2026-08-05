package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

/** cp41 code-collision: on a customerCode collision, append '-&lt;n&gt;' (smallest n &gt;= 2) to keep it
 *  unique. A genuine hash collision cannot be forced black-box (it needs an identical
 *  normalizedTelephone + lastName, which telephone-uniqueness already blocks), so assert the rule's
 *  guarantee instead: distinct owners always get distinct customerCodes. */
@Tag("cp41")
class Cp41Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodesStayUnique() throws Exception {
		String c1 = fetchOwner(createOwnerOk(withPostcode(ownerNode()))).get("customerCode").asText();
		String c2 = fetchOwner(createOwnerOk(withPostcode(ownerNode()))).get("customerCode").asText();
		assertNotEquals(c1, c2);
	}
}
